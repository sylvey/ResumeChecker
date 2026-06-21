package Resume

import (
	"bytes"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/ledongthuc/pdf"
)

type ParsedResume struct {
	Name            string `json:"Name"`
	Email           string `json:"Email"`
	Education       string `json:"Education"`
	TechnicalSkills string `json:"Technical Skills"`
	Experience      string `json:"Experience"`
}

type ParsedJobDescription struct {
	JobDescription string `json:"Job Description Text"`
}

type ParseResult struct {
	Resume         ParsedResume         `json:"parsed_resume"`
	JobDescription ParsedJobDescription `json:"parsed_job_description"`
}

var ParseHandler = func(c *gin.Context) {

	jdText := c.PostForm("job_description")
	if jdText == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "job_description field is required"})
		return
	}
	parsedJD := ParsedJobDescription{JobDescription: jdText}

	// 2. Extract and validate the PDF resume file
	file, err := c.FormFile("resume_file")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "resume_file field is required"})
		return
	}
	if filepath.Ext(file.Filename) != ".pdf" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "resume_file must be a PDF document"})
		return
	}

	// 3. Save the uploaded file temporarily
	tempFile, err := os.CreateTemp("", "resume-*.pdf")
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create temp file"})
		return
	}
	defer os.Remove(tempFile.Name())

	if err := c.SaveUploadedFile(file, tempFile.Name()); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to save uploaded file"})
		return
	}

	// 4. Extract text from the PDF
	resumeText, err := extractTextFromPDF(tempFile.Name())
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to parse PDF content"})
		return
	}

	// 5. Parse the resume into specific sections
	parsedResume := parseResumeSections(resumeText)

	// 6. Return the final structured result
	result := ParseResult{
		Resume:         parsedResume,
		JobDescription: parsedJD,
	}

	c.JSON(http.StatusOK, result)
}

func extractTextFromPDF(path string) (string, error) {
	f, r, err := pdf.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()

	var buf bytes.Buffer
	b, err := r.GetPlainText()
	if err != nil {
		return "", err
	}
	buf.ReadFrom(b)
	return buf.String(), nil
}

// parseResumeSections uses section headers to block out the text
func parseResumeSections(text string) ParsedResume {
	var parsed ParsedResume

	// Extract Email using Regex
	emailRegex := regexp.MustCompile(`[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}`)
	if match := emailRegex.FindString(text); match != "" {
		parsed.Email = match
	}

	lines := strings.Split(text, "\n")
	var currentSection string
	var educationBuilder, skillsBuilder, expBuilder strings.Builder

	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" {
			continue
		}

		// Heuristic for Name: Grab the very first non-empty line
		if parsed.Name == "" && !strings.Contains(trimmed, "PAGE") {
			parsed.Name = trimmed
			continue
		}

		// Identify Sections based on exact header matches
		upperLine := strings.ToUpper(trimmed)
		if upperLine == "EDUCATION" || upperLine == "TECHNICAL SKILLS" || upperLine == "EXPERIENCE" || upperLine == "PROJECTS" {
			currentSection = upperLine
			continue
		}

		// Route text to the appropriate builder based on the current section
		switch currentSection {
		case "EDUCATION":
			educationBuilder.WriteString(trimmed + "\n")
		case "TECHNICAL SKILLS":
			skillsBuilder.WriteString(trimmed + "\n")
		case "EXPERIENCE":
			expBuilder.WriteString(trimmed + "\n")
		}
	}

	parsed.Education = strings.TrimSpace(educationBuilder.String())
	parsed.TechnicalSkills = strings.TrimSpace(skillsBuilder.String())
	parsed.Experience = strings.TrimSpace(expBuilder.String())

	return parsed
}
