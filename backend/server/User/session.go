package User

import (
	// "net/http"

	"github.com/gin-gonic/gin"
)

// CurrentUserID reads the session cookie, validates the JWT, and returns
// the logged-in user's ID as a hex string. The one place cookie/JWT parsing
// happens -- every other auth check in this codebase (MeHandler's
// currentUserID included) is built on top of this rather than re-parsing.
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