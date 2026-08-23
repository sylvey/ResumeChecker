package User

import (
	"context"
	"net/http"
	"time"

	"server/models"

	"github.com/gin-gonic/gin"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
	"google.golang.org/api/idtoken"
)

var userCollection *mongo.Collection
var googleClientID string

func InitUserCollection(db *mongo.Database, clientID string, jwtSecretStr string) {
	userCollection = db.Collection("users")
	googleClientID = clientID
	jwtSecret = []byte(jwtSecretStr)

	userCollection.Indexes().CreateOne(context.Background(), mongo.IndexModel{
		Keys:    bson.M{"google_id": 1},
		Options: options.Index().SetUnique(true),
	})
}

type GoogleLoginReq struct {
	IDToken string `json:"id_token" binding:"required"`
}

func GoogleLoginHandler(c *gin.Context) {
	var req GoogleLoginReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	payload, err := idtoken.Validate(context.Background(), req.IDToken, googleClientID)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "invalid google token"})
		return
	}

	googleID := payload.Subject
	email, _ := payload.Claims["email"].(string)
	name, _ := payload.Claims["name"].(string)
	picture, _ := payload.Claims["picture"].(string)

	user, err := findOrCreateUser(c, googleID, email, name, picture)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "db error"})
		return
	}

	token, err := issueSessionJWT(user)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "jwt error"})
		return
	}

	c.SetCookie("session", token, 3600*24*7, "/", "", true, true)
	// 第五個參數 secure=false 是因為你 localhost 開發用 http，正式環境要改 true

	c.JSON(http.StatusOK, gin.H{"user": user})
}

func findOrCreateUser(ctx context.Context, googleID, email, name, picture string) (*models.User, error) {
	filter := bson.M{"google_id": googleID}
	update := bson.M{
		"$set": bson.M{
			"email":   email,
			"name":    name,
			"picture": picture,
		},
		"$setOnInsert": bson.M{
			"google_id":  googleID,
			"created_at": time.Now(),
		},
	}
	opts := options.FindOneAndUpdate().
		SetUpsert(true).
		SetReturnDocument(options.After)

	var user models.User
	err := userCollection.FindOneAndUpdate(ctx, filter, update, opts).Decode(&user)
	if err != nil {
		return nil, err
	}
	return &user, nil
}

func MeHandler(c *gin.Context) {
	cookie, err := c.Cookie("session")
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "not logged in"})
		return
	}

	claims, err := parseSessionJWT(cookie)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "invalid session"})
		return
	}

	objID, _ := primitive.ObjectIDFromHex(claims.UserID)
	var user models.User
	err = userCollection.FindOne(context.Background(), bson.M{"_id": objID}).Decode(&user)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "user not found"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"user": user})
}

func LogoutHandler(c *gin.Context) {
	c.SetCookie("session", "", -1, "/", "", false, true)
	c.JSON(http.StatusOK, gin.H{"message": "logged out"})
}