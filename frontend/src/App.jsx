import { useState, useEffect } from "react";
import reactLogo from "./assets/react.svg";
import viteLogo from "./assets/vite.svg";
import heroImg from "./assets/hero.png";
import "./App.css";
import { TextField, Box, Button } from "@mui/material";
import pkg from "file-uploader-js";
const FileUploader = pkg.default;
import axios from "axios";

function App() {
  const [resume, setResume] = useState(null);
  const [jd, setJd] = useState(null);

  useEffect(() => {
    if (jd) {
      console.log("jd:", jd);
    }
  }, [jd]);

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!resume) {
      alert("Please upload your resume.");
      return;
    }
    if (!jd) {
      alert("Please enter the job description.");
      return;
    }
    console.log("Resume:", resume);
    console.log("Job Description:", jd);

    // 1. Create a new FormData object
    const formData = new FormData();
    
    // 2. Append your data exactly matching the keys the Go backend expects
    formData.append("resume_file", resume);
    formData.append("job_description", jd);

    try {
      // 3. Send the formData object directly instead of a generic {} object
      const res = await axios.post("http://localhost:8080/api/parse", formData);
      console.log(res.data);
    } catch (error) {
      console.error("Error uploading data:", error);
    }
  };

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
