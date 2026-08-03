package User

import (
	// "net/http"

	"github.com/gin-gonic/gin"
)

// CurrentUserID reads the session cookie, validates the JWT, and returns
// the logged-in user's ID as a hex string. Exported so other packages
// (Resume, etc.) can gate handlers on login without duplicating the
// cookie/JWT logic that MeHandler already has.
func CurrentUserID(c *gin.Context) (string, bool) {
	cookie, err := c.Cookie("session")
	if err != nil {
		return "", false
	}

	claims, err := parseSessionJWT(cookie)
	if err != nil {
		return "", false
	}

	return claims.UserID, true
}