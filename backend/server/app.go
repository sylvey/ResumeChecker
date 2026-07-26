package main

import (
	"server/Resume"
	"server/sample"
	"time"

	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
)

func main() {
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

	r.GET("/api/parse/:jobId/status", Resume.ScoreStatusHandler)

	r.Run(":8080")
}
