package Resume

import (
	"context"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"server/User"

	"github.com/gin-gonic/gin"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

const MaxSavedResumes = 3

var (
	ResumesColl     *mongo.Collection
	JDColl          *mongo.Collection
	ResultsColl     *mongo.Collection
	AnnotationsColl *mongo.Collection
	storageDir      string
)

// resumeStorageDir is where saved (user-owned) resume PDFs live on EC2.
// Only populated when the user explicitly saves -- unsaved score runs never
// touch this directory, they stay as tempfiles on the Python side and get


func InitCollections(db *mongo.Database) {
	ResumesColl = db.Collection("resumes")
	JDColl = db.Collection("job_descriptions")
	ResultsColl = db.Collection("score_results")
	AnnotationsColl = db.Collection("annotations")

	storageDir = "data/resumes"
	if err := os.MkdirAll(storageDir, 0o755); err != nil {
		log.Printf("warning: failed to create resume storage dir %s: %v", storageDir, err)
	}



	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	ResumesColl.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{{Key: "user_id", Value: 1}},
		Options: options.Index().SetName("by_user"),
	})
}

// SaveResumeHandler is hit only when the user clicks "Save this resume".
// The frontend re-sends the actual PDF bytes (still held in React state
// from the original upload) plus the resume_id it got back from /score, so
// the saved file's identity lines up with the annotations already stored
// under that resume_id.
var SaveResumeHandler = func(c *gin.Context) {
	if ResumesColl == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "ResumesColl not initialized — Resume.InitCollections(db) was not called in main.go"})
		return
	}
	userID, ok := User.CurrentUserID(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "login required"})
		return
	}

	resumeID := c.PostForm("resume_id")
	if resumeID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "resume_id is required"})
		return
	}

	file, err := c.FormFile("resume_file")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "resume_file is required"})
		return
	}
	if filepath.Ext(file.Filename) != ".pdf" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "resume_file must be a PDF document"})
		return
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	count, err := ResumesColl.CountDocuments(ctx, bson.M{"user_id": userID})
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to check saved resumes"})
		return
	}
	if count >= MaxSavedResumes {
		c.JSON(http.StatusConflict, gin.H{
			"error": "You can save up to 3 resumes. Delete one before saving a new one.",
		})
		return
	}

	src, err := file.Open()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to read uploaded file"})
		return
	}
	defer src.Close()

	storagePath := filepath.Join(storageDir, resumeID+".pdf")
	dst, err := os.Create(storagePath)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to store file"})
		return
	}
	defer dst.Close()
	if _, err := io.Copy(dst, src); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to store file"})
		return
	}

	_, err = ResumesColl.UpdateOne(ctx,
		bson.M{"_id": resumeID},
		bson.M{"$set": bson.M{
			"_id":          resumeID,
			"filename":     file.Filename,
			"storage_path": storagePath,
			"user_id":      userID,
			"saved_at":     time.Now(),
		}},
		options.Update().SetUpsert(true),
	)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to save resume record"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"status": "saved"})
}

// ListResumesHandler returns every resume the current user has saved --
// up to MaxSavedResumes, regardless of whether any of them back a saved
// result. This is what the "delete a saved resume" UI lists from, since a
// resume can be saved without its result ever being saved too.
var ListResumesHandler = func(c *gin.Context) {
	if ResumesColl == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "ResumesColl not initialized"})
		return
	}
	userID, ok := User.CurrentUserID(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "login required"})
		return
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	cursor, err := ResumesColl.Find(ctx, bson.M{"user_id": userID})
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to list resumes"})
		return
	}
	defer cursor.Close(ctx)

	type resumeDoc struct {
		ID       string    `bson:"_id" json:"resume_id"`
		Filename string    `bson:"filename" json:"filename"`
		SavedAt  time.Time `bson:"saved_at" json:"saved_at"`
	}
	var resumes []resumeDoc
	if err := cursor.All(ctx, &resumes); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to decode resumes"})
		return
	}

	c.JSON(http.StatusOK, resumes)
}

// DeleteResumeHandler removes a saved resume -- its Mongo record and its
// PDF on disk. Blocked if any saved result still references it, so the
// dashboard's guarantee (every saved result has a real resume behind it)
// can't be broken by deleting out from under it.
var DeleteResumeHandler = func(c *gin.Context) {
	if ResumesColl == nil || ResultsColl == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "collections not initialized"})
		return
	}
	userID, ok := User.CurrentUserID(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "login required"})
		return
	}
	resumeID := c.Param("id")

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	var resume struct {
		StoragePath string `bson:"storage_path"`
		UserID      string `bson:"user_id"`
	}
	if err := ResumesColl.FindOne(ctx, bson.M{"_id": resumeID}).Decode(&resume); err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "resume not found"})
		return
	}
	if resume.UserID != userID {
		c.JSON(http.StatusForbidden, gin.H{"error": "not your resume"})
		return
	}

	blockingResults, err := ResultsColl.CountDocuments(ctx, bson.M{"resume_id": resumeID, "user_id": userID})
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to check saved results"})
		return
	}
	if blockingResults > 0 {
		c.JSON(http.StatusConflict, gin.H{
			"error": "This resume backs a saved result. Delete that result first.",
		})
		return
	}

	if _, err := ResumesColl.DeleteOne(ctx, bson.M{"_id": resumeID}); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to delete resume record"})
		return
	}
	if resume.StoragePath != "" {
		if err := os.Remove(resume.StoragePath); err != nil && !os.IsNotExist(err) {
			log.Printf("warning: failed to remove resume file %s: %v", resume.StoragePath, err)
		}
	}

	c.JSON(http.StatusOK, gin.H{"status": "deleted"})
}

// SaveResultHandler is hit only when the user clicks "Save this result".
// A result's resume must already be saved (via SaveResumeHandler) before
// its result can be -- otherwise the dashboard table would have a score
// with no resume file behind its icon. JD text needs no equivalent check:
// it's readable straight off the result via DownloadJDHandler, not gated
// behind its own saved flag.
var SaveResultHandler = func(c *gin.Context) {
	if ResultsColl == nil || ResumesColl == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "collections not initialized"})
		return
	}
	userID, ok := User.CurrentUserID(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "login required"})
		return
	}
	var body struct {
		JobID string `json:"job_id" binding:"required"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "job_id is required"})
		return
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	var result struct {
		ResumeID string `bson:"resume_id"`
	}
	if err := ResultsColl.FindOne(ctx, bson.M{"_id": body.JobID}).Decode(&result); err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "result not found"})
		return
	}

	savedResumeCount, err := ResumesColl.CountDocuments(ctx, bson.M{"_id": result.ResumeID, "user_id": userID})
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to check saved resume"})
		return
	}
	if savedResumeCount == 0 {
		c.JSON(http.StatusConflict, gin.H{"error": "Save this resume before saving its result."})
		return
	}

	res, err := ResultsColl.UpdateOne(ctx,
		bson.M{"_id": body.JobID},
		bson.M{"$set": bson.M{"user_id": userID}},
	)
	if err != nil || res.MatchedCount == 0 {
		c.JSON(http.StatusNotFound, gin.H{"error": "result not found"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"status": "saved"})
}

// DeleteResultHandler un-saves a result -- just the score_results doc, no
// file to remove. Needed so DeleteResumeHandler's "delete that result
// first" is actually actionable, not another dead-end message.
var DeleteResultHandler = func(c *gin.Context) {
	if ResultsColl == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "ResultsColl not initialized"})
		return
	}
	userID, ok := User.CurrentUserID(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "login required"})
		return
	}
	jobID := c.Param("jobId")

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	res, err := ResultsColl.DeleteOne(ctx, bson.M{"_id": jobID, "user_id": userID})
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to delete result"})
		return
	}
	if res.DeletedCount == 0 {
		c.JSON(http.StatusNotFound, gin.H{"error": "result not found"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"status": "deleted"})
}

// ListResultsHandler returns the current user's saved results -- one row
// per scoring, the dashboard table's main data source. Each row's resume
// is guaranteed to have a filename (SaveResultHandler enforces the resume
// was saved first); JD text and the full score breakdown are fetched
// separately, on demand, to keep this list light.
var ListResultsHandler = func(c *gin.Context) {
	if ResultsColl == nil || ResumesColl == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "collections not initialized"})
		return
	}
	userID, ok := User.CurrentUserID(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "login required"})
		return
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	cursor, err := ResultsColl.Find(ctx, bson.M{"user_id": userID})
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to list results"})
		return
	}
	defer cursor.Close(ctx)

	type resultDoc struct {
		JobID        string    `bson:"_id" json:"job_id"`
		ResumeID     string    `bson:"resume_id" json:"resume_id"`
		JDID         string    `bson:"jd_id" json:"jd_id"`
		OverallScore float64   `bson:"overall_score" json:"overall_score"`
		Reply        string    `bson:"reply" json:"reply"`
		CreatedAt    time.Time `bson:"created_at" json:"created_at"`
	}
	var results []resultDoc
	if err := cursor.All(ctx, &results); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to decode results"})
		return
	}

	type row struct {
		resultDoc
		ResumeFilename string `json:"resume_filename"`
		CompanyName    string `json:"company_name,omitempty"`
		Position       string `json:"position,omitempty"`
	}
	rows := make([]row, 0, len(results))
	for _, r := range results {
		var resume struct {
			Filename string `bson:"filename"`
		}
		ResumesColl.FindOne(ctx, bson.M{"_id": r.ResumeID}).Decode(&resume)

		var jd struct {
			CompanyName string `bson:"company_name"`
			Position    string `bson:"position"`
		}
		if JDColl != nil {
			JDColl.FindOne(ctx, bson.M{"_id": r.JDID}).Decode(&jd)
		}

		rows = append(rows, row{
			resultDoc:      r,
			ResumeFilename: resume.Filename,
			CompanyName:    jd.CompanyName,
			Position:       jd.Position,
		})
	}

	c.JSON(http.StatusOK, rows)
}

// DownloadResumeHandler streams a saved resume's PDF back to its owner.
var DownloadResumeHandler = func(c *gin.Context) {
	if ResumesColl == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "ResumesColl not initialized"})
		return
	}
	userID, ok := User.CurrentUserID(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "login required"})
		return
	}
	resumeID := c.Param("id")

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	var resume struct {
		Filename    string `bson:"filename"`
		StoragePath string `bson:"storage_path"`
		UserID      string `bson:"user_id"`
	}
	if err := ResumesColl.FindOne(ctx, bson.M{"_id": resumeID}).Decode(&resume); err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "resume not found"})
		return
	}
	if resume.UserID != userID {
		c.JSON(http.StatusForbidden, gin.H{"error": "not your resume"})
		return
	}

	c.FileAttachment(resume.StoragePath, resume.Filename)
}

// DownloadJDHandler streams a job description's raw text back. JDs aren't
// separately saved -- authorized instead by the requester owning a saved
// result that references this jd_id.
var DownloadJDHandler = func(c *gin.Context) {
	if JDColl == nil || ResultsColl == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "collections not initialized"})
		return
	}
	userID, ok := User.CurrentUserID(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "login required"})
		return
	}
	jdID := c.Param("id")

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	owned, err := ResultsColl.CountDocuments(ctx, bson.M{"jd_id": jdID, "user_id": userID})
	if err != nil || owned == 0 {
		c.JSON(http.StatusForbidden, gin.H{"error": "not your job description"})
		return
	}

	var jd struct {
		JDText string `bson:"jd_text"`
	}
	if err := JDColl.FindOne(ctx, bson.M{"_id": jdID}).Decode(&jd); err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "job description not found"})
		return
	}

	c.Header("Content-Disposition", `attachment; filename="jd_`+jdID+`.txt"`)
	c.Data(http.StatusOK, "text/plain", []byte(jd.JDText))
}

// ResultDetailHandler returns the full resume-section x JD-section
// breakdown for one saved result, pulled from the annotations Python
// writes during scoring. The table row only carries the overall score --
// this is fetched on demand when the user wants the detail view/download.
var ResultDetailHandler = func(c *gin.Context) {
	if ResultsColl == nil || AnnotationsColl == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "collections not initialized"})
		return
	}
	userID, ok := User.CurrentUserID(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "login required"})
		return
	}
	jobID := c.Param("jobId")

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	var result struct {
		ResumeID string `bson:"resume_id"`
		JDID     string `bson:"jd_id"`
		UserID   string `bson:"user_id"`
	}
	if err := ResultsColl.FindOne(ctx, bson.M{"_id": jobID}).Decode(&result); err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "result not found"})
		return
	}
	if result.UserID != userID {
		c.JSON(http.StatusForbidden, gin.H{"error": "not your result"})
		return
	}

	cursor, err := AnnotationsColl.Find(ctx, bson.M{"resume_id": result.ResumeID, "jd_id": result.JDID})
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to fetch detail"})
		return
	}
	defer cursor.Close(ctx)

	var pairs []bson.M
	if err := cursor.All(ctx, &pairs); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to decode detail"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"pairs": pairs})
}