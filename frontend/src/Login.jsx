// Login.js
import { Dialog, DialogContent, DialogTitle, IconButton } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import { GoogleLogin } from "@react-oauth/google";
import axios from "axios";

export default function Login({ open, onClose, onLoginSuccess }) {
  const handleGoogleSuccess = async (res) => {
    try {
      const { data } = await axios.post(
        "/api/auth/google",
        { id_token: res.credential },
        { withCredentials: true },
      );
      onLoginSuccess(data.user);
      onClose();
    } catch (err) {
      console.error("Login failed", err);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        Login
        <IconButton onClick={onClose} size="small">
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent sx={{ display: "flex", justifyContent: "center", pb: 4 }}>
        <GoogleLogin
          onSuccess={handleGoogleSuccess}
          onError={() => console.error("Google login failed")}
        />
      </DialogContent>
    </Dialog>
  );
}
