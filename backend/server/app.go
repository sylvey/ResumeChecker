package main

import ("github.com/gin-gonic/gin"
	"server/sample")

func main(){
	r := gin.Default()

	r.GET("/sample/hello", sample.Sample_hello)

	r.POST("/sample/echo", sample.Sample_echo)

	r.Run(":8080")
}

