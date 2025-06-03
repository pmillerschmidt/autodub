import React, { useState } from "react";
import axios from "axios";

function App() {
  const [url, setUrl] = useState("");
  const [lang, setLang] = useState("es");
  const [loading, setLoading] = useState(false);
  const [currentStep, setCurrentStep] = useState("");
  const [outputUrl, setOutputUrl] = useState("");
  const [keepBackground, setKeepBackground] = useState(false);
  const [cloneVoice, setCloneVoice] = useState(false);

  const handleSubmit = async () => {
    setLoading(true);
    setCurrentStep("");
    setOutputUrl("");

    setCurrentStep("Processing...");
    try {
      const response = await axios.post("http://localhost:8000/dub", {
        url,
        target_lang: lang,
        keep_background: keepBackground,
        clone_voice: cloneVoice,
      });

      const { output_url, steps } = response.data;
      for (let step of steps) {
        setCurrentStep(step);
        await new Promise((res) => setTimeout(res, 800)); // optional short delay between step updates
      }
      
      setCurrentStep("Completed!");
      setOutputUrl(output_url || "");
    } catch (err) {
      console.error("Dubbing failed:", err);
      setCurrentStep("Error during processing. Check backend logs.");
    }
    setLoading(false);
  };

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      padding: '2rem',
      backgroundColor: '#f5f5f5',
      fontFamily: 'Arial, sans-serif'
    }}>
      <h1 style={{ color: '#333', marginBottom: '2rem' }}>AutoDub</h1>

      {!loading && !outputUrl && (
        <div style={{
          maxWidth: '800px',
          width: '100%',
          backgroundColor: 'white',
          padding: '2rem',
          borderRadius: '10px',
          boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
        }}>
          <div style={{
            display: 'flex',
            gap: '1rem',
            marginBottom: '1rem',
            flexWrap: 'wrap',
            justifyContent: 'center'
          }}>
            <input
              type="text"
              placeholder="YouTube URL"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              style={{
                padding: '0.8rem',
                borderRadius: '5px',
                border: '1px solid #ddd',
                flex: '1',
                minWidth: '300px'
              }}
            />
            <select
              value={lang}
              onChange={(e) => setLang(e.target.value)}
              style={{
                padding: '0.8rem',
                borderRadius: '5px',
                border: '1px solid #ddd',
                backgroundColor: 'white'
              }}
            >
              <option value="es">Spanish</option>
              <option value="fr">French</option>
              <option value="de">German</option>
              <option value="ja">Japanese</option>
            </select>
          </div>

          <div style={{
            display: 'flex',
            justifyContent: 'center',
            gap: '2rem',
            marginBottom: '1.5rem'
          }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <input
                type="checkbox"
                checked={keepBackground}
                onChange={(e) => setKeepBackground(e.target.checked)}
              />
              Keep background audio
            </label>

            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <input
                type="checkbox"
                checked={cloneVoice}
                onChange={(e) => setCloneVoice(e.target.checked)}
              />
              Clone voices
            </label>
          </div>

          <button
            onClick={handleSubmit}
            style={{
              padding: '0.8rem 2rem',
              backgroundColor: '#007bff',
              color: 'white',
              border: 'none',
              borderRadius: '5px',
              cursor: 'pointer',
              transition: 'background-color 0.2s'
            }}
            onMouseOver={(e) => e.target.style.backgroundColor = '#0056b3'}
            onMouseOut={(e) => e.target.style.backgroundColor = '#007bff'}
          >
            Dub
          </button>
        </div>
      )}

      {loading && (
        <div style={{
          marginTop: '4rem',
          textAlign: 'center',
          color: '#555',
          fontSize: '1.2rem'
        }}>
          <p>{currentStep}</p>
        </div>
      )}

      {outputUrl && (
        <div style={{
          marginTop: '2rem',
          display: 'flex',
          justifyContent: 'center',
          width: '100%'
        }}>
          <video
            controls
            src={`http://localhost:8000${outputUrl}`}
            style={{
              maxWidth: '100%',
              borderRadius: '5px',
              boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
            }}
          />
        </div>
      )}
    </div>
  );
}

export default App;
