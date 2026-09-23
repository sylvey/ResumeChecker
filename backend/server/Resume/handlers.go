package Resume

import (
	"bytes"
	"context"
	"io"
	"mime/multipart"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"server/User"

	"github.com/gin-gonic/gin"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo/options"
)

// scoreServiceBaseURL is where the Python Flask agent pipeline listens.
// Override with the SCORE_SERVICE_URL env var if it runs elsewhere.
// Uses 127.0.0.1 rather than "localhost" so it can't accidentally resolve to
// some other IPv6 listener squatting on the same port (e.g. Docker Desktop).
func scoreServiceBaseURL() string {
	if url := os.Getenv("SCORE_SERVICE_URL"); url != "" {
		return url
	}
	return "http://127.0.0.1:5001"
}

// The agent runs a multi-step Claude tool loop that can take tens of seconds,
// so give the forwarded request a generous timeout.
var httpClient = &http.Client{Timeout: 5 * time.Minute}

// anonymousAttemptAllowed atomically increments the attempt counter for this
// IP and reports whether it's still within MaxAnonymousAttempts. Using
// FindOneAndUpdate with $inc (rather than count-then-insert) makes the
// increment-and-check a single atomic operation, so two simultaneous
// requests from the same IP can't both slip through the check.
func anonymousAttemptAllowed(c *gin.Context) (bool, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	var doc struct {
		Attempts int `bson:"attempts"`
	}
	err := AnonymousAttemptsColl.FindOneAndUpdate(
		ctx,
		bson.M{"_id": c.ClientIP()},
		bson.M{"$inc": bson.M{"attempts": 1}},
		options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After),
	).Decode(&doc)
	if err != nil {
		return false, err
	}
	return doc.Attempts <= MaxAnonymousAttempts, nil
}

// resumeSourceError carries the HTTP status a resolveResumeSource failure
// should map to, so ParseHandler doesn't have to re-derive it.
type resumeSourceError struct {
	status int
	msg    string
}

func (e *resumeSourceError) Error() string { return e.msg }

func resumeSourceErrorResponse(err error) (int, string) {
	if rse, ok := err.(*resumeSourceError); ok {
		return rse.status, rse.msg
	}
	return http.StatusInternalServerError, "Failed to read resume"
}

// resolveResumeSource returns the filename and a reader for the resume to
// score -- either a saved resume (savedResumeID, ownership-checked against
// userID) or the uploaded resume_file field. The returned close func must
// always be called, even on error (where it's a no-op), to release the file
// handle.
func resolveResumeSource(c *gin.Context, savedResumeID, userID string) (string, io.Reader, func(), error) {
	noop := func() {}

	if savedResumeID != "" {
		var resume struct {
			Filename    string `bson:"filename"`
			StoragePath string `bson:"storage_path"`
			UserID      string `bson:"user_id"`
		}
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := ResumesColl.FindOne(ctx, bson.M{"_id": savedResumeID}).Decode(&resume); err != nil {
			return "", nil, noop, &resumeSourceError{http.StatusNotFound, "saved resume not found"}
		}
		if resume.UserID != userID {
			return "", nil, noop, &resumeSourceError{http.StatusForbidden, "not your resume"}
		}
		f, err := os.Open(resume.StoragePath)
		if err != nil {
			return "", nil, noop, &resumeSourceError{http.StatusInternalServerError, "failed to read saved resume"}
		}
		return resume.Filename, f, func() { f.Close() }, nil
	}

	file, err := c.FormFile("resume_file")
	if err != nil {
		return "", nil, noop, &resumeSourceError{http.StatusBadRequest, "resume_file field is required"}
	}
	if filepath.Ext(file.Filename) != ".pdf" {
		return "", nil, noop, &resumeSourceError{http.StatusBadRequest, "resume_file must be a PDF document"}
	}
	src, err := file.Open()
	if err != nil {
		return "", nil, noop, &resumeSourceError{http.StatusInternalServerError, "Failed to read uploaded file"}
	}
	return file.Filename, src, func() { src.Close() }, nil
}

// ParseHandler validates the resume + job description and forwards them to
// the Python scoring service, relaying its response back to the caller.
// The resume is either a fresh upload (resume_file) or a reference to one
// already saved (saved_resume_id) -- see resolveResumeSource.
var ParseHandler = func(c *gin.Context) {
	userID, loggedIn := User.CurrentUserID(c)

	savedResumeID := c.PostForm("saved_resume_id")
	if savedResumeID != "" && !loggedIn {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "login required to use a saved resume"})
		return
	}

	// 0. Anonymous requests are cost-limited -- each one is a real, paid
	// Claude API call. Logged-in users aren't subject to this.
	if !loggedIn {
		allowed, err := anonymousAttemptAllowed(c)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to check usage limit"})
			return
		}
		if !allowed {
			c.JSON(http.StatusTooManyRequests, gin.H{
				"error": "You've used your free scoring attempt. Log in to score more resumes.",
			})
			return
		}
	}

	// 1. Validate the job description text.
	jdText := c.PostForm("job_description")
	if jdText == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "job_description field is required"})
		return
	}

	// Optional -- when given, the scoring service uses these as the
	// authoritative job title instead of inferring one from jd_text.
	companyName := c.PostForm("company_name")
	position := c.PostForm("position")

	// 2. Resolve the resume: either a saved one (by reference) or a fresh
	// upload.
	resumeFilename, resumeReader, closeReader, err := resolveResumeSource(c, savedResumeID, userID)
	if err != nil {
		status, msg := resumeSourceErrorResponse(err)
		c.JSON(status, gin.H{"error": msg})
		return
	}
	defer closeReader()

	// 3. Rebuild the multipart form so it can be forwarded to the scoring
	//    service with the same field names the frontend sent.
	var body bytes.Buffer
	writer := multipart.NewWriter(&body)

	if err := writer.WriteField("job_description", jdText); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to build scoring request"})
		return
	}
	if err := writer.WriteField("company_name", companyName); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to build scoring request"})
		return
	}
	if err := writer.WriteField("position", position); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to build scoring request"})
		return
	}
	if savedResumeID != "" {
		// Reuse the saved resume's own ID for this run, so its results land
		// under a resume_id already saved to the user's account -- see
		// server.py's /score route.
		if err := writer.WriteField("resume_id", savedResumeID); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to build scoring request"})
			return
		}
	}

	part, err := writer.CreateFormFile("resume_file", resumeFilename)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to build scoring request"})
		return
	}
	if _, err := io.Copy(part, resumeReader); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to copy resume file"})
		return
	}
	if err := writer.Close(); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to finalize scoring request"})
		return
	}

	// 4. POST to the Flask scoring service.
	req, err := http.NewRequest(http.MethodPost, scoreServiceBaseURL()+"/score", &body)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create scoring request"})
		return
	}
	req.Header.Set("Content-Type", writer.FormDataContentType())

	resp, err := httpClient.Do(req)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": "Scoring service unavailable: " + err.Error()})
		return
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": "Failed to read scoring service response"})
		return
	}

	// 5. Relay the scoring service's status code and JSON body back to the caller.
	contentType := resp.Header.Get("Content-Type")
	if contentType == "" {
		contentType = "application/json"
	}
	c.Data(resp.StatusCode, contentType, respBody)
}

// ScoreStatusHandler polls the Python scoring service for a job's progress
// and relays its response back to the caller.
var ScoreStatusHandler = func(c *gin.Context) {
	jobID := c.Param("jobId")

	resp, err := httpClient.Get(scoreServiceBaseURL() + "/score/" + jobID + "/status")
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": "Scoring service unavailable: " + err.Error()})
		return
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": "Failed to read scoring service response"})
		return
	}

	contentType := resp.Header.Get("Content-Type")
	if contentType == "" {
		contentType = "application/json"
	}
	c.Data(resp.StatusCode, contentType, respBody)
}
