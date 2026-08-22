package main

import (
	"context"
	"log"
	// "os"
	"time"

	"server/Resume"
	"server/sample"
	"server/User"

	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
	"github.com/joho/godotenv"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

func main() {
	envMap, err := godotenv.Read()
	if err != nil {
		log.Fatal("failed to read .env file:", err)
	}

	mongoURI := envMap["MONGO_URI"]
	if mongoURI == "" {
		log.Fatal("MONGO_URI is not set in .env")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	client, err := mongo.Connect(ctx, options.Client().ApplyURI(mongoURI))
	if err != nil {
		log.Fatal("mongo connect failed:", err)
	}
	db := client.Database("resumechecker")
	User.InitUserCollection(db, envMap["GOOGLE_CLIENT_ID"])
	Resume.InitCollections(db) 


	r := gin.Default()
	r.Use(cors.New(cors.Config{
		AllowOrigins:     []string{"http://localhost:5173"}, // Explicitly allow your frontend origin
		AllowMethods:     []string{"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"},
		AllowHeaders:     []string{"Origin", "Content-Type", "Accept"},
		ExposeHeaders:    []string{"Content-Length"},
		AllowCredentials: true,
		MaxAge:           12 * time.Hour, // Cache the preflight request for 12 hours
	}))

	r.GET("/sample/hello", sample.Sample_hello)

	r.POST("/sample/echo", sample.Sample_echo)

	r.POST("/api/parse", Resume.ParseHandler)
	r.POST("/api/auth/google", User.GoogleLoginHandler)


	r.GET("/api/parse/:jobId/status", Resume.ScoreStatusHandler)
	r.GET("/api/auth/me", User.MeHandler)
	r.POST("/api/auth/logout", User.LogoutHandler)

	r.POST("/api/resumes/save", Resume.SaveResumeHandler)
	r.POST("/api/results/save", Resume.SaveResultHandler)

	r.GET("/api/results/mine", Resume.ListResultsHandler)
	r.GET("/api/resumes/mine", Resume.ListResumesHandler)
	r.GET("/api/resumes/:id/download", Resume.DownloadResumeHandler)
	r.GET("/api/jds/:id/download", Resume.DownloadJDHandler)
	r.GET("/api/results/:jobId/detail", Resume.ResultDetailHandler)
	r.DELETE("/api/resumes/:id", Resume.DeleteResumeHandler)
	r.DELETE("/api/results/:jobId", Resume.DeleteResultHandler)

	r.Run(":8080")
}
