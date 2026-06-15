import { useCallback, useEffect, useState } from "react";
import { SPENCER_API_BASE } from "../utils/constants";

export function useObsidianBrain() {
  const [brainStatus, setBrainStatus] = useState(null);
  const [graph, setGraph] = useState({ nodes: [], edges: [] });
  const [results, setResults] = useState([]);
  const [status, setStatus] = useState("loading");
  const [message, setMessage] = useState("");

  const loadStatus = useCallback(async () => {
    setStatus("loading");
    try {
      const response = await fetch(`${SPENCER_API_BASE}/api/brain/status`, { cache: "no-store" });
      if (!response.ok) throw new Error("Brain status unavailable");
      const data = await response.json();
      setBrainStatus(data);
      setStatus("ready");
    } catch (error) {
      setMessage(error.message || "Brain status unavailable");
      setStatus("error");
    }
  }, []);

  const loadGraph = useCallback(async () => {
    try {
      const response = await fetch(`${SPENCER_API_BASE}/api/brain/graph`, { cache: "no-store" });
      if (!response.ok) throw new Error("Brain graph unavailable");
      const data = await response.json();
      setGraph({
        nodes: Array.isArray(data.nodes) ? data.nodes : [],
        edges: Array.isArray(data.edges) ? data.edges : [],
      });
    } catch {
      setGraph({ nodes: [], edges: [] });
    }
  }, []);

  const search = useCallback(async (query) => {
    const clean = query.trim();
    if (!clean) {
      setResults([]);
      return;
    }
    setStatus("searching");
    try {
      const response = await fetch(
        `${SPENCER_API_BASE}/api/brain/search?q=${encodeURIComponent(clean)}&limit=10`,
        { cache: "no-store" },
      );
      if (!response.ok) throw new Error("Brain search failed");
      const data = await response.json();
      setResults(data.results || []);
      setMessage(data.results?.length ? "" : "No matching vault evidence found.");
      setStatus("ready");
    } catch (error) {
      setMessage(error.message || "Brain search failed");
      setStatus("error");
    }
  }, []);

  const capture = useCallback(async ({ title, content, kind }) => {
    try {
      const response = await fetch(`${SPENCER_API_BASE}/api/brain/capture`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Spencer-Confirm": "capture-memory",
        },
        body: JSON.stringify({
          confirmed: true,
          title,
          content,
          kind,
          source: "Spencer webapp",
          confidence: "unverified",
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Memory capture failed");
      setMessage(`Captured ${data.wikilink} for review.`);
      await Promise.all([loadStatus(), loadGraph()]);
      return data;
    } catch (error) {
      setMessage(error.message || "Memory capture failed");
      throw error;
    }
  }, [loadGraph, loadStatus]);

  const reindex = useCallback(async () => {
    try {
      const response = await fetch(`${SPENCER_API_BASE}/api/brain/reindex`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Brain reindex failed");
      setMessage(`Indexed ${data.noteCount} notes.`);
      await Promise.all([loadStatus(), loadGraph()]);
    } catch (error) {
      setMessage(error.message || "Brain reindex failed");
    }
  }, [loadGraph, loadStatus]);

  useEffect(() => {
    loadStatus();
    loadGraph();
    const graphRefresh = window.setInterval(loadGraph, 15_000);
    return () => window.clearInterval(graphRefresh);
  }, [loadGraph, loadStatus]);

  return {
    brainStatus,
    graph,
    results,
    status,
    message,
    loadStatus,
    loadGraph,
    search,
    capture,
    reindex,
  };
}
