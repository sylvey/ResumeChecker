package Resume

import (
	"bytes"
	"io"
	"mime/multipart"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"github.com/gin-gonic/gin"
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

// ParseHandler validates the uploaded resume + job description and forwards them
// to the Python scoring service, relaying its response back to the caller.
var ParseHandler = func(c *gin.Context) {
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

	// 2. Validate the uploaded PDF resume.
	file, err := c.FormFile("resume_file")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "resume_file field is required"})
		return
	}
	if filepath.Ext(file.Filename) != ".pdf" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "resume_file must be a PDF document"})
		return
	}

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

	src, err := file.Open()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to read uploaded file"})
		return
	}
	defer src.Close()

	part, err := writer.CreateFormFile("resume_file", file.Filename)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to build scoring request"})
		return
	}
	if _, err := io.Copy(part, src); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to copy uploaded file"})
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
