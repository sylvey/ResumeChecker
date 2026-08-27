package Resume

import (
	"bytes"
	"context"
	"encoding/json"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"

	"server/User"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

// Signs tokens the same way User.issueSessionJWT does, using User.Claims
// directly -- that type is exported, so tests don't need any production
// code changes just to mint a valid session cookie.
const testJWTSecret = "go-test-secret-do-not-use-in-prod"

var testDB *mongo.Database

func TestMain(m *testing.M) {
	uri := os.Getenv("MONGO_URI")
	if uri == "" {
		uri = "mongodb://localhost:27017"
	}
	client, err := mongo.Connect(context.Background(), options.Client().ApplyURI(uri))
	if err != nil {
		panic(err)
	}
	// A package-specific database name -- go test ./... runs different
	// packages' test binaries in parallel by default, and TestMain's
	// teardown below drops the whole database. A name shared with another
	// package's tests (e.g. User's) means whichever one finishes first can
	// drop the database out from under the other mid-run.
	testDB = client.Database("resumechecker_test_resume")

	InitCollections(testDB)
	User.InitUserCollection(testDB, "unused-google-client-id", testJWTSecret)

	code := m.Run()

	testDB.Drop(context.Background())
	os.RemoveAll(storageDir)
	os.Exit(code)
}

func resetCollections(t *testing.T) {
	t.Helper()
	ctx := context.Background()
	for _, name := range []string{"resumes", "job_descriptions", "score_results", "annotations"} {
		if _, err := testDB.Collection(name).DeleteMany(ctx, bson.M{}); err != nil {
			t.Fatalf("failed to reset %s: %v", name, err)
		}
	}
}

func sessionCookie(userID string) *http.Cookie {
	claims := User.Claims{
		UserID: userID,
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
		},
	}
	signed, err := jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString([]byte(testJWTSecret))
	if err != nil {
		panic(err)
	}
	return &http.Cookie{Name: "session", Value: signed}
}

func newRouter() *gin.Engine {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.POST("/api/resumes/save", SaveResumeHandler)
	r.POST("/api/results/save", SaveResultHandler)
	r.GET("/api/resumes/mine", ListResumesHandler)
	r.GET("/api/results/mine", ListResultsHandler)
	r.GET("/api/resumes/:id/download", DownloadResumeHandler)
	r.GET("/api/jds/:id/download", DownloadJDHandler)
	r.GET("/api/results/:jobId/detail", ResultDetailHandler)
	r.DELETE("/api/resumes/:id", DeleteResumeHandler)
	r.DELETE("/api/results/:jobId", DeleteResultHandler)
	return r
}

func saveResumeRequest(t *testing.T, resumeID string, cookie *http.Cookie) *http.Request {
	t.Helper()
	var body bytes.Buffer
	w := multipart.NewWriter(&body)
	if err := w.WriteField("resume_id", resumeID); err != nil {
		t.Fatal(err)
	}
	part, err := w.CreateFormFile("resume_file", "resume.pdf")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := part.Write([]byte("%PDF-1.4 fake pdf contents")); err != nil {
		t.Fatal(err)
	}
	if err := w.Close(); err != nil {
		t.Fatal(err)
	}

	req := httptest.NewRequest(http.MethodPost, "/api/resumes/save", &body)
	req.Header.Set("Content-Type", w.FormDataContentType())
	if cookie != nil {
		req.AddCookie(cookie)
	}
	return req
}

// insertResume inserts a saved-resume record directly, bypassing the
// multipart upload -- most tests only care that a resume row with this
// owner exists, not the file-storage side effects.
func insertResume(t *testing.T, resumeID, userID string) {
	t.Helper()
	_, err := ResumesColl.InsertOne(context.Background(), bson.M{
		"_id":      resumeID,
		"filename": resumeID + ".pdf",
		"user_id":  userID,
		"saved_at": time.Now(),
	})
	if err != nil {
		t.Fatalf("failed to insert resume fixture: %v", err)
	}
}

func insertResult(t *testing.T, jobID, resumeID, jdID, userID string, score float64) {
	t.Helper()
	_, err := ResultsColl.InsertOne(context.Background(), bson.M{
		"_id":           jobID,
		"resume_id":     resumeID,
		"jd_id":         jdID,
		"overall_score": score,
		"reply":         "",
		"user_id":       userID,
		"created_at":    time.Now(),
	})
	if err != nil {
		t.Fatalf("failed to insert result fixture: %v", err)
	}
}

func insertJD(t *testing.T, jdID, jdText string) {
	t.Helper()
	_, err := JDColl.InsertOne(context.Background(), bson.M{
		"_id":      jdID,
		"jd_text":  jdText,
		"user_id":  nil,
		"saved_at": time.Now(),
	})
	if err != nil {
		t.Fatalf("failed to insert JD fixture: %v", err)
	}
}

func decodeError(t *testing.T, rec *httptest.ResponseRecorder) string {
	t.Helper()
	var body struct {
		Error string `json:"error"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("failed to decode error body %q: %v", rec.Body.String(), err)
	}
	return body.Error
}

func TestSaveResumeHandler_RequiresAuth(t *testing.T) {
	resetCollections(t)
	router := newRouter()

	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, saveResumeRequest(t, "resume-1", nil))

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestSaveResumeHandler_EnforcesMaxCap(t *testing.T) {
	resetCollections(t)
	router := newRouter()
	cookie := sessionCookie("user-cap-test")

	for i, id := range []string{"resume-a", "resume-b", "resume-c"} {
		rec := httptest.NewRecorder()
		router.ServeHTTP(rec, saveResumeRequest(t, id, cookie))
		if rec.Code != http.StatusOK {
			t.Fatalf("save %d: expected 200, got %d: %s", i, rec.Code, rec.Body.String())
		}
	}

	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, saveResumeRequest(t, "resume-d", cookie))
	if rec.Code != http.StatusConflict {
		t.Fatalf("4th save: expected 409, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestSaveResultHandler_RequiresResumeSavedFirst(t *testing.T) {
	resetCollections(t)
	router := newRouter()
	cookie := sessionCookie("user-1")

	// The result exists (as if Python's scoring pipeline wrote it), but its
	// resume was never saved via SaveResumeHandler.
	insertResult(t, "job-1", "resume-unsaved", "jd-1", "", 8.5)

	body, _ := json.Marshal(map[string]string{"job_id": "job-1"})
	req := httptest.NewRequest(http.MethodPost, "/api/results/save", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.AddCookie(cookie)

	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusConflict {
		t.Fatalf("expected 409, got %d: %s", rec.Code, rec.Body.String())
	}
	if got := decodeError(t, rec); got != "Save this resume before saving its result." {
		t.Errorf("unexpected error message: %q", got)
	}
}

func TestSaveResultHandler_SucceedsOnceResumeSaved(t *testing.T) {
	resetCollections(t)
	router := newRouter()
	cookie := sessionCookie("user-2")

	insertResume(t, "resume-2", "user-2")
	insertResult(t, "job-2", "resume-2", "jd-2", "", 7.1)

	body, _ := json.Marshal(map[string]string{"job_id": "job-2"})
	req := httptest.NewRequest(http.MethodPost, "/api/results/save", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.AddCookie(cookie)

	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var stored struct {
		UserID string `bson:"user_id"`
	}
	if err := ResultsColl.FindOne(context.Background(), bson.M{"_id": "job-2"}).Decode(&stored); err != nil {
		t.Fatalf("failed to reload result: %v", err)
	}
	if stored.UserID != "user-2" {
		t.Errorf("expected result to be stamped with user-2, got %q", stored.UserID)
	}
}

func TestDeleteResumeHandler_BlockedByExistingResult(t *testing.T) {
	resetCollections(t)
	router := newRouter()
	cookie := sessionCookie("user-3")

	insertResume(t, "resume-3", "user-3")
	insertResult(t, "job-3", "resume-3", "jd-3", "user-3", 6.0)

	req := httptest.NewRequest(http.MethodDelete, "/api/resumes/resume-3", nil)
	req.AddCookie(cookie)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusConflict {
		t.Fatalf("expected 409, got %d: %s", rec.Code, rec.Body.String())
	}
	if got := decodeError(t, rec); got != "This resume backs a saved result. Delete that result first." {
		t.Errorf("unexpected error message: %q", got)
	}

	// The resume must still exist -- the block should be a no-op, not a
	// partial delete.
	count, err := ResumesColl.CountDocuments(context.Background(), bson.M{"_id": "resume-3"})
	if err != nil {
		t.Fatalf("count failed: %v", err)
	}
	if count != 1 {
		t.Errorf("expected resume-3 to still exist, count=%d", count)
	}
}

func TestDeleteResumeHandler_SucceedsOnceResultDeleted(t *testing.T) {
	resetCollections(t)
	router := newRouter()
	cookie := sessionCookie("user-4")

	insertResume(t, "resume-4", "user-4")

	req := httptest.NewRequest(http.MethodDelete, "/api/resumes/resume-4", nil)
	req.AddCookie(cookie)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	count, err := ResumesColl.CountDocuments(context.Background(), bson.M{"_id": "resume-4"})
	if err != nil {
		t.Fatalf("count failed: %v", err)
	}
	if count != 0 {
		t.Errorf("expected resume-4 to be gone, count=%d", count)
	}
}

func TestDownloadResumeHandler_ForbiddenForOtherUser(t *testing.T) {
	resetCollections(t)
	router := newRouter()

	insertResume(t, "resume-5", "owner")

	req := httptest.NewRequest(http.MethodGet, "/api/resumes/resume-5/download", nil)
	req.AddCookie(sessionCookie("someone-else"))
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusForbidden {
		t.Fatalf("expected 403, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestDeleteResultHandler_DoesNotDeleteAnotherUsersResult(t *testing.T) {
	resetCollections(t)
	router := newRouter()

	insertResult(t, "job-6", "resume-6", "jd-6", "owner", 5.5)

	req := httptest.NewRequest(http.MethodDelete, "/api/results/job-6", nil)
	req.AddCookie(sessionCookie("someone-else"))
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d: %s", rec.Code, rec.Body.String())
	}
	count, err := ResultsColl.CountDocuments(context.Background(), bson.M{"_id": "job-6"})
	if err != nil {
		t.Fatalf("count failed: %v", err)
	}
	if count != 1 {
		t.Errorf("expected job-6 to survive another user's delete attempt, count=%d", count)
	}
}

func TestResultDetailHandler_ForbiddenForOtherUser(t *testing.T) {
	resetCollections(t)
	router := newRouter()

	insertResult(t, "job-7", "resume-7", "jd-7", "owner", 9.0)

	req := httptest.NewRequest(http.MethodGet, "/api/results/job-7/detail", nil)
	req.AddCookie(sessionCookie("someone-else"))
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusForbidden {
		t.Fatalf("expected 403, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestDownloadJDHandler_RequiresOwningResult(t *testing.T) {
	resetCollections(t)
	router := newRouter()

	insertJD(t, "jd-8", "job description text")

	// Nobody has a saved result referencing jd-8 yet, so nobody is
	// authorized to read it -- not even a logged-in user.
	req := httptest.NewRequest(http.MethodGet, "/api/jds/jd-8/download", nil)
	req.AddCookie(sessionCookie("some-user"))
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusForbidden {
		t.Fatalf("expected 403, got %d: %s", rec.Code, rec.Body.String())
	}

	// Once that user has a saved result referencing jd-8, they're authorized.
	insertResult(t, "job-8", "resume-8", "jd-8", "some-user", 4.0)

	req2 := httptest.NewRequest(http.MethodGet, "/api/jds/jd-8/download", nil)
	req2.AddCookie(sessionCookie("some-user"))
	rec2 := httptest.NewRecorder()
	router.ServeHTTP(rec2, req2)

	if rec2.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec2.Code, rec2.Body.String())
	}
	if rec2.Body.String() != "job description text" {
		t.Errorf("unexpected JD body: %q", rec2.Body.String())
	}
}

func TestListResumesHandler_ScopedToCurrentUser(t *testing.T) {
	resetCollections(t)
	router := newRouter()

	insertResume(t, "resume-9a", "user-9")
	insertResume(t, "resume-9b", "user-9")
	insertResume(t, "resume-9c", "someone-else")

	req := httptest.NewRequest(http.MethodGet, "/api/resumes/mine", nil)
	req.AddCookie(sessionCookie("user-9"))
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var got []struct {
		ResumeID string `json:"resume_id"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &got); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if len(got) != 2 {
		t.Fatalf("expected 2 resumes scoped to user-9, got %d", len(got))
	}
}