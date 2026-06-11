package sample

import "github.com/gin-gonic/gin"

var Sample_hello = func(c *gin.Context) {
		c.JSON(200, gin.H{
			"message": "Hello World",
		})
	}

var Sample_echo = func(c *gin.Context) {
		var body map[string]any
		c.BindJSON(&body)
		c.JSON(200, body)
	}