import { useEffect, useState } from "react";

export default function App() {
  const [ping, setPing] = useState("(sin probar)");
  const [email, setEmail] = useState("carlos@ejemplo.com");
  const [question, setQuestion] = useState("");
  const [log, setLog] = useState([]);

  const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

  const addLog = (msg) => setLog((l) => [...l, msg]);

  // 1) probar /ping al cargar
  useEffect(() => {
    fetch(`${API}/ping`)
      .then((r) => r.json())
      .then((d) => setPing(d.message))
      .catch(() => setPing("error (revisa backend)"));
  }, [API]);

  // 2) enviar pregunta a /aura/ask
  const askAura = async () => {
    const q = question.trim();
    if (!q || !email.trim()) return;
    addLog(`Tú: ${q}`);
    setQuestion("");

    try {
      const r = await fetch(`${API}/aura/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ usuario_correo: email, pregunta: q }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || "Error en /aura/ask");
      addLog(`Aura: ${data.respuesta}`);
    } catch (e) {
      addLog(`Error: ${e.message}`);
    }
  };

  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      askAura();
    }
  };

  return (
    <div style={styles.wrap}>
      <h1>Aura (frontend)</h1>

      <div style={styles.row}>
        <strong>Backend /ping:</strong>
        <span>{ping}</span>
        <button style={styles.btn}
          onClick={() => {
            fetch(`${API}/ping`)
              .then((r) => r.json())
              .then((d) => setPing(d.message))
              .catch(() => setPing("error"));
          }}>
          Reintentar
        </button>
      </div>

      <div style={styles.row}>
        <label style={styles.label}>Correo:</label>
        <input
          style={styles.input}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="usuario@uabcs.mx"
        />
      </div>

      <div style={styles.col}>
        <textarea
          style={{ ...styles.input, height: 90 }}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Escribe tu pregunta para Aura y presiona Enter…"
        />
        <button style={styles.btnPrimary} onClick={askAura}>Preguntar</button>
      </div>

      <div style={styles.log}>
        {log.map((l, i) => (
          <div key={i} style={styles.line}>{l}</div>
        ))}
      </div>
    </div>
  );
}

const styles = {
  wrap: { maxWidth: 800, margin: "24px auto", fontFamily: "system-ui" },
  row: { display: "flex", gap: 10, alignItems: "center", marginBottom: 12 },
  col: { display: "grid", gap: 8, marginBottom: 16 },
  label: { minWidth: 70 },
  input: { flex: 1, padding: 8, borderRadius: 8, border: "1px solid #ccc" },
  btn: { padding: "8px 12px", borderRadius: 8, border: 0, background: "#e5e7eb" },
  btnPrimary: { padding: "10px 14px", borderRadius: 8, border: 0, background: "#10b981", color: "#042", fontWeight: 700 },
  log: { border: "1px solid #ddd", borderRadius: 8, padding: 10, minHeight: 160, whiteSpace: "pre-wrap" },
  line: { marginBottom: 6 },
};
