import { useState, useEffect } from "react";
import reactLogo from "./assets/react.svg";
import viteLogo from "./assets/vite.svg";
import heroImg from "./assets/hero.png";
import "./App.css";
import { TextField, Box, Button } from "@mui/material";
import pkg from "file-uploader-js";
const FileUploader = pkg.default;

function App() {
  const [resume, setResume] = useState(null);
  const [jd, setJd] = useState(null);

  useEffect(() => {
    if (jd) {
      console.log("jd:", jd);
    }
  }, [jd]);

  const onSubmit = (e) => {};

  return (
    <>
      <Box sx={{ width: "100%" }}>
        <h3>Upload Your Resume</h3>
        {resume ? (
          <div style={{ marginTop: "20px" }}>
            <p>Selected Resume:</p>
            <p>
              {resume.name} {(resume.size / 1024).toFixed(2)} KB
            </p>
          </div>
        ) : (
          <FileUploader
            accept={[".pdf"]}
            uploadedFileCallback={(file) => console.log(file)}
            renderInput={({ onChange, accept }) => (
              <div>
                <button
                  onClick={() => document.getElementById("fileInput").click()}
                  style={{
                    flex: "1",
                    padding: "10px 20px",
                    background: "#77b2f11b",
                    color: "black",
                    border: "none",
                    borderRadius: "5px",
                    cursor: "pointer",
                  }}
                >
                  📁 Upload your Resume
                </button>
                <input
                  id="fileInput"
                  type="file"
                  accept={accept}
                  onChange={(e) => {
                    setResume(e.target.files[0]);
                  }}
                  style={{ display: "none" }}
                />
              </div>
            )}
          />
        )}
      </Box>
      <Box sx={{ width: "100%", marginTop: "20px" }}>
        <h3>Job Description</h3>
        <TextField
          label="Job Description"
          multiline
          rows={4}
          onChange={(e) => {
            setJd(e.target.value);
          }}
          variant="outlined"
          fullWidth
          style={{ width: "70%" }}
        />
      </Box>
      <Box sx={{ width: "100%", marginTop: "20px" }}>
        <Button
          sx={{
            width: "90px",
            background: "hsl(210, 100%, 45%)",
            color: "white",
          }}
          onClick={onSubmit}
        >
          Submit
        </Button>
      </Box>
    </>
  );
}

export default App;
