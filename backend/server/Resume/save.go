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
	ResumesColl *mongo.Collection
	JDColl      *mongo.Collection
	ResultsColl *mongo.Collection
	storageDir  string
)

// resumeStorageDir is where saved (user-owned) resume PDFs live on EC2.
// Only populated when the user explicitly saves -- unsaved score runs never
// touch this directory, they stay as tempfiles on the Python side and get


func InitCollections(db *mongo.Database) {
	ResumesColl = db.Collection("resumes")
	JDColl = db.Collection("job_descriptions")
	ResultsColl = db.Collection("score_results")

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

var SaveJDHandler = func(c *gin.Context) {
	if JDColl == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "JDColl not initialized"})
		return
	}
	userID, ok := User.CurrentUserID(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "login required"})
		return
	}
	var body struct {
		JDID string `json:"jd_id" binding:"required"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "jd_id is required"})
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	res, err := JDColl.UpdateOne(ctx,
		bson.M{"_id": body.JDID},
		bson.M{"$set": bson.M{"user_id": userID}},
	)
	if err != nil || res.MatchedCount == 0 {
		c.JSON(http.StatusNotFound, gin.H{"error": "job description not found"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"status": "saved"})
}

var SaveResultHandler = func(c *gin.Context) {
	if ResultsColl == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "ResultsColl not initialized"})
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