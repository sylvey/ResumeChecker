package User

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"

	"server/models"

	"github.com/gin-gonic/gin"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

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
	testDB = client.Database("resumechecker_test")

	InitUserCollection(testDB, "unused-google-client-id", testJWTSecret)

	code := m.Run()

	testDB.Drop(context.Background())
	os.Exit(code)
}

func resetUsers(t *testing.T) {
	t.Helper()
	if _, err := userCollection.DeleteMany(context.Background(), bson.M{}); err != nil {
		t.Fatalf("failed to reset users: %v", err)
	}
}

func insertUser(t *testing.T, googleID, email, name string) primitive.ObjectID {
	t.Helper()
	res, err := userCollection.InsertOne(context.Background(), bson.M{
		"google_id":  googleID,
		"email":      email,
		"name":       name,
		"picture":    "",
		"created_at": time.Now(),
	})
	if err != nil {
		t.Fatalf("failed to insert user fixture: %v", err)
	}
	return res.InsertedID.(primitive.ObjectID)
}

// sessionCookieFor mints a real session cookie via the package's own
// issueSessionJWT -- since this file lives in package User, it can call
// that directly rather than reconstructing the signing logic externally.
func sessionCookieFor(t *testing.T, objID primitive.ObjectID) *http.Cookie {
	t.Helper()
	token, err := issueSessionJWT(&models.User{ID: objID})
	if err != nil {
		t.Fatalf("failed to mint session token: %v", err)
	}
	return &http.Cookie{Name: "session", Value: token}
}

func newRouter() *gin.Engine {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.GET("/api/auth/me", MeHandler)
	r.PATCH("/api/auth/me", UpdateProfileHandler)
	r.POST("/api/auth/logout", LogoutHandler)
	r.POST("/api/auth/google", GoogleLoginHandler)
	return r
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

func TestMeHandler_RequiresAuth(t *testing.T) {
	resetUsers(t)
	router := newRouter()

	req := httptest.NewRequest(http.MethodGet, "/api/auth/me", nil)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d: %s", rec.Code, rec.Body.String())
	}
	if got := decodeError(t, rec); got != "not logged in" {
		t.Errorf("unexpected error message: %q", got)
	}
}

func TestMeHandler_RejectsGarbageCookie(t *testing.T) {
	resetUsers(t)
	router := newRouter()

	req := httptest.NewRequest(http.MethodGet, "/api/auth/me", nil)
	req.AddCookie(&http.Cookie{Name: "session", Value: "garbage"})
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestMeHandler_ReturnsCurrentUser(t *testing.T) {
	resetUsers(t)
	router := newRouter()

	objID := insertUser(t, "google-1", "a@example.com", "Ada")
	cookie := sessionCookieFor(t, objID)

	req := httptest.NewRequest(http.MethodGet, "/api/auth/me", nil)
	req.AddCookie(cookie)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var body struct {
		User models.User `json:"user"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if body.User.Email != "a@example.com" {
		t.Errorf("expected email a@example.com, got %q", body.User.Email)
	}
}

func TestMeHandler_ValidSessionForDeletedUser(t *testing.T) {
	resetUsers(t)
	router := newRouter()

	// A valid, unexpired token for a user that no longer exists in the DB --
	// e.g. the account was deleted after the cookie was issued.
	cookie := sessionCookieFor(t, primitive.NewObjectID())

	req := httptest.NewRequest(http.MethodGet, "/api/auth/me", nil)
	req.AddCookie(cookie)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d: %s", rec.Code, rec.Body.String())
	}
	if got := decodeError(t, rec); got != "user not found" {
		t.Errorf("unexpected error message: %q", got)
	}
}

func TestUpdateProfileHandler_RequiresAuth(t *testing.T) {
	resetUsers(t)
	router := newRouter()

	body, _ := json.Marshal(map[string]string{"bio": "hi"})
	req := httptest.NewRequest(http.MethodPatch, "/api/auth/me", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestUpdateProfileHandler_UpdatesFieldsAndPersists(t *testing.T) {
	resetUsers(t)
	router := newRouter()

	objID := insertUser(t, "google-2", "b@example.com", "Bea")
	cookie := sessionCookieFor(t, objID)

	payload, _ := json.Marshal(map[string]string{
		"bio":      "Backend engineer.",
		"linkedin": "https://linkedin.com/in/bea",
		"website":  "https://bea.dev",
	})
	req := httptest.NewRequest(http.MethodPatch, "/api/auth/me", bytes.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	req.AddCookie(cookie)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var stored models.User
	if err := userCollection.FindOne(context.Background(), bson.M{"_id": objID}).Decode(&stored); err != nil {
		t.Fatalf("failed to reload user: %v", err)
	}
	if stored.Bio != "Backend engineer." || stored.LinkedIn != "https://linkedin.com/in/bea" || stored.Website != "https://bea.dev" {
		t.Errorf("profile fields did not persist correctly: %+v", stored)
	}
	// Fields untouched by the update must survive it.
	if stored.Email != "b@example.com" {
		t.Errorf("expected email to be untouched, got %q", stored.Email)
	}
}

func TestUpdateProfileHandler_RejectsMalformedJSON(t *testing.T) {
	resetUsers(t)
	router := newRouter()

	objID := insertUser(t, "google-3", "c@example.com", "Cy")
	cookie := sessionCookieFor(t, objID)

	req := httptest.NewRequest(http.MethodPatch, "/api/auth/me", bytes.NewReader([]byte("not json")))
	req.Header.Set("Content-Type", "application/json")
	req.AddCookie(cookie)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestLogoutHandler_ClearsCookie(t *testing.T) {
	router := newRouter()

	req := httptest.NewRequest(http.MethodPost, "/api/auth/logout", nil)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	found := false
	for _, c := range rec.Result().Cookies() {
		if c.Name == "session" {
			found = true
			if c.MaxAge >= 0 {
				t.Errorf("expected session cookie to be expired (negative MaxAge), got %d", c.MaxAge)
			}
		}
	}
	if !found {
		t.Error("expected logout response to set a session-clearing cookie")
	}
}

// GoogleLoginHandler's success/invalid-token paths both call
// idtoken.Validate, which fetches Google's public keys over the network --
// not suitable for a fast, reliable unit test. Only the pure
// input-validation path (missing id_token, fails before any network call)
// is covered here.
func TestGoogleLoginHandler_RequiresIDToken(t *testing.T) {
	router := newRouter()

	req := httptest.NewRequest(http.MethodPost, "/api/auth/google", bytes.NewReader([]byte("{}")))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestFindOrCreateUser_UpsertsThenUpdatesMutableFields(t *testing.T) {
	resetUsers(t)
	ctx := context.Background()

	created, err := findOrCreateUser(ctx, "google-4", "d1@example.com", "Dee", "pic1")
	if err != nil {
		t.Fatalf("first findOrCreateUser failed: %v", err)
	}
	if created.Email != "d1@example.com" {
		t.Fatalf("expected new user with email d1@example.com, got %q", created.Email)
	}

	updated, err := findOrCreateUser(ctx, "google-4", "d2@example.com", "Dee Updated", "pic2")
	if err != nil {
		t.Fatalf("second findOrCreateUser failed: %v", err)
	}
	if updated.ID != created.ID {
		t.Errorf("expected same user ID across calls, got %v vs %v", created.ID, updated.ID)
	}
	if updated.Email != "d2@example.com" || updated.Name != "Dee Updated" || updated.Picture != "pic2" {
		t.Errorf("expected mutable fields to update, got %+v", updated)
	}
	if updated.GoogleID != "google-4" {
		t.Errorf("expected google_id to stay google-4, got %q", updated.GoogleID)
	}

	count, err := userCollection.CountDocuments(ctx, bson.M{"google_id": "google-4"})
	if err != nil {
		t.Fatalf("count failed: %v", err)
	}
	if count != 1 {
		t.Errorf("expected exactly one user document for google-4, got %d", count)
	}
}