import { useEffect, useRef } from "react";

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

const hash = (value) => {
  let result = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    result ^= value.charCodeAt(index);
    result = Math.imul(result, 16777619);
  }
  return result >>> 0;
};

// Cooling thresholds — the simulation settles, then holds perfectly still
// (exactly like Obsidian's graph view). Interaction re-heats it briefly.
const ALPHA_MIN = 0.004;
const ALPHA_START = 1;
const ALPHA_REHEAT = 0.35;

const buildSimulation = (graph) => {
  const nodes = (graph?.nodes || []).map((node, index, list) => {
    const seed = hash(node.id);
    const angle = ((seed % 10_000) / 10_000) * Math.PI * 2;
    const ring = 58 + ((seed >>> 8) % 190);
    const spread = 0.72 + (index / Math.max(list.length - 1, 1)) * 0.28;
    return {
      ...node,
      degree: 0,
      x: Math.cos(angle) * ring * spread,
      y: Math.sin(angle) * ring * spread,
      vx: 0,
      vy: 0,
    };
  });
  const nodeIndex = new Map(nodes.map((node, index) => [node.id, index]));
  const edges = (graph?.edges || [])
    .map((edge) => ({
      source: nodeIndex.get(edge.source),
      target: nodeIndex.get(edge.target),
    }))
    .filter((edge) => edge.source !== undefined && edge.target !== undefined);

  edges.forEach((edge) => {
    nodes[edge.source].degree += 1;
    nodes[edge.target].degree += 1;
  });
  return { nodes, edges, alpha: ALPHA_START };
};

export function ObsidianBrainGraph({ graph }) {
  const canvasRef = useRef(null);
  const frameRef = useRef(null);
  const simulationRef = useRef({ nodes: [], edges: [], alpha: 0 });
  const transformRef = useRef({ x: 0, y: 0, scale: 1 });
  const interactionRef = useRef({
    mode: null, node: -1, pointerX: 0, pointerY: 0, panX: 0, panY: 0, hover: -1,
  });
  const visibleRef = useRef(true);
  // The render loop is always scheduled but cheap: it only runs physics while
  // the simulation is still cooling, and only repaints when something changed.
  // dirtyRef requests a repaint; reheatRef re-energises the layout.
  const dirtyRef = useRef(true);
  const reheatRef = useRef(() => {});

  useEffect(() => {
    simulationRef.current = buildSimulation(graph);
    transformRef.current = { x: 0, y: 0, scale: 1 };
    dirtyRef.current = true;
  }, [graph]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const context = canvas.getContext("2d");
    let previousTime = performance.now();

    const observer = new IntersectionObserver(
      ([entry]) => {
        const wasVisible = visibleRef.current;
        visibleRef.current = entry.isIntersecting;
        if (!wasVisible && entry.isIntersecting) dirtyRef.current = true;
      },
      { threshold: 0.02 },
    );
    observer.observe(canvas);

    const stepPhysics = (elapsed) => {
      const sim = simulationRef.current;
      const { nodes, edges } = sim;
      const interaction = interactionRef.current;
      if (!nodes.length || sim.alpha <= ALPHA_MIN) return false;

      const forces = nodes.map(() => ({ x: 0, y: 0 }));

      // Repulsion (O(n^2), but only runs while the sim is still cooling).
      for (let a = 0; a < nodes.length; a += 1) {
        for (let b = a + 1; b < nodes.length; b += 1) {
          const dx = nodes[b].x - nodes[a].x;
          const dy = nodes[b].y - nodes[a].y;
          const distanceSquared = Math.max(dx * dx + dy * dy, 36);
          const distance = Math.sqrt(distanceSquared);
          const strength = 118 / distanceSquared;
          const fx = (dx / distance) * strength;
          const fy = (dy / distance) * strength;
          forces[a].x -= fx; forces[a].y -= fy;
          forces[b].x += fx; forces[b].y += fy;
        }
      }

      // Spring along edges.
      edges.forEach((edge) => {
        const source = nodes[edge.source];
        const target = nodes[edge.target];
        const dx = target.x - source.x;
        const dy = target.y - source.y;
        const distance = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
        const strength = (distance - 42) * 0.0018;
        const fx = (dx / distance) * strength;
        const fy = (dy / distance) * strength;
        forces[edge.source].x += fx; forces[edge.source].y += fy;
        forces[edge.target].x -= fx; forces[edge.target].y -= fy;
      });

      // Integrate — forces and gentle centering scale with alpha, so motion
      // fades to nothing. No orbit term: the graph never drifts on its own.
      nodes.forEach((node, index) => {
        if (interaction.mode === "node" && interaction.node === index) return;
        node.vx = (node.vx + (forces[index].x - node.x * 0.00035) * sim.alpha) * 0.9;
        node.vy = (node.vy + (forces[index].y - node.y * 0.00035) * sim.alpha) * 0.9;
        node.x += node.vx * elapsed;
        node.y += node.vy * elapsed;
      });

      sim.alpha *= Math.pow(0.97, elapsed);
      if (sim.alpha <= ALPHA_MIN) {
        sim.alpha = 0;
        nodes.forEach((node) => { node.vx = 0; node.vy = 0; });
      }
      return true;
    };

    const drawScene = (rect, pixelRatio) => {
      const { nodes, edges } = simulationRef.current;
      const interaction = interactionRef.current;
      context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
      context.clearRect(0, 0, rect.width, rect.height);
      const transform = transformRef.current;
      const centerX = rect.width / 2 + transform.x;
      const centerY = rect.height / 2 + transform.y;

      context.strokeStyle = "rgba(0, 0, 0, 0.18)";
      context.lineWidth = 0.72;
      edges.forEach((edge) => {
        const source = nodes[edge.source];
        const target = nodes[edge.target];
        context.beginPath();
        context.moveTo(centerX + source.x * transform.scale, centerY + source.y * transform.scale);
        context.lineTo(centerX + target.x * transform.scale, centerY + target.y * transform.scale);
        context.stroke();
      });

      nodes.forEach((node, index) => {
        const hovered = interaction.hover === index;
        const radius = (1.65 + Math.min(2.25, Math.sqrt(node.degree) * 0.42) + (hovered ? 2 : 0))
          * clamp(transform.scale, 0.7, 1.35);
        context.fillStyle = "#000000";
        context.beginPath();
        context.arc(
          centerX + node.x * transform.scale,
          centerY + node.y * transform.scale,
          radius, 0, Math.PI * 2,
        );
        context.fill();
      });
    };

    const draw = (time) => {
      // Always reschedule — the loop stays alive but is near-free when idle, so
      // interaction is always picked up and nothing can freeze.
      frameRef.current = requestAnimationFrame(draw);
      if (!visibleRef.current) return;

      const elapsed = clamp((time - previousTime) / 16.67, 0.2, 1.8);
      previousTime = time;

      const moved = stepPhysics(elapsed);          // only while cooling
      if (moved) dirtyRef.current = true;
      const interaction = interactionRef.current;
      if (interaction.mode != null) dirtyRef.current = true;

      if (!dirtyRef.current) return;                // settled + unchanged: draw nothing

      const rect = canvas.getBoundingClientRect();
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 1.5);
      const width = Math.max(1, Math.round(rect.width * pixelRatio));
      const height = Math.max(1, Math.round(rect.height * pixelRatio));
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }
      drawScene(rect, pixelRatio);
      if (!moved && interaction.mode == null) dirtyRef.current = false;
    };

    reheatRef.current = () => {
      const sim = simulationRef.current;
      sim.alpha = Math.max(sim.alpha, ALPHA_REHEAT);
      dirtyRef.current = true;
    };
    frameRef.current = requestAnimationFrame(draw);

    return () => {
      observer.disconnect();
      if (frameRef.current != null) cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
      reheatRef.current = () => {};
    };
  }, []);

  const reheat = () => reheatRef.current();

  const nearestNode = (clientX, clientY) => {
    const canvas = canvasRef.current;
    if (!canvas) return -1;
    const rect = canvas.getBoundingClientRect();
    const transform = transformRef.current;
    const centerX = rect.width / 2 + transform.x;
    const centerY = rect.height / 2 + transform.y;
    let nearest = -1;
    let nearestDistance = 14;
    simulationRef.current.nodes.forEach((node, index) => {
      const dx = clientX - rect.left - (centerX + node.x * transform.scale);
      const dy = clientY - rect.top - (centerY + node.y * transform.scale);
      const distance = Math.sqrt(dx * dx + dy * dy);
      if (distance < nearestDistance) {
        nearest = index;
        nearestDistance = distance;
      }
    });
    return nearest;
  };

  const pointerToWorld = (clientX, clientY) => {
    const rect = canvasRef.current.getBoundingClientRect();
    const transform = transformRef.current;
    return {
      x: (clientX - rect.left - rect.width / 2 - transform.x) / transform.scale,
      y: (clientY - rect.top - rect.height / 2 - transform.y) / transform.scale,
    };
  };

  const handlePointerDown = (event) => {
    const node = nearestNode(event.clientX, event.clientY);
    interactionRef.current = {
      ...interactionRef.current,
      mode: node >= 0 ? "node" : "pan",
      node,
      pointerX: event.clientX,
      pointerY: event.clientY,
      panX: transformRef.current.x,
      panY: transformRef.current.y,
    };
    if (node >= 0) {
      const point = pointerToWorld(event.clientX, event.clientY);
      const target = simulationRef.current.nodes[node];
      target.x = point.x;
      target.y = point.y;
      target.vx = 0;
      target.vy = 0;
    }
    event.currentTarget.setPointerCapture(event.pointerId);
    dirtyRef.current = true;
  };

  const handlePointerMove = (event) => {
    const interaction = interactionRef.current;
    if (interaction.mode === "node" && interaction.node >= 0) {
      const point = pointerToWorld(event.clientX, event.clientY);
      const target = simulationRef.current.nodes[interaction.node];
      target.x = point.x;
      target.y = point.y;
      target.vx = 0;
      target.vy = 0;
      reheat(); // let neighbours follow, then re-settle
      return;
    }
    if (interaction.mode === "pan") {
      transformRef.current.x = interaction.panX + event.clientX - interaction.pointerX;
      transformRef.current.y = interaction.panY + event.clientY - interaction.pointerY;
      dirtyRef.current = true;
      return;
    }
    const previousHover = interaction.hover;
    interaction.hover = nearestNode(event.clientX, event.clientY);
    if (interaction.hover !== previousHover) dirtyRef.current = true;
  };

  const stopInteraction = (event) => {
    interactionRef.current.mode = null;
    interactionRef.current.node = -1;
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    dirtyRef.current = true;
  };

  const handleWheel = (event) => {
    event.preventDefault();
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const transform = transformRef.current;
    const before = pointerToWorld(event.clientX, event.clientY);
    transform.scale = clamp(transform.scale * Math.exp(-event.deltaY * 0.001), 0.45, 2.6);
    transform.x = event.clientX - rect.left - rect.width / 2 - before.x * transform.scale;
    transform.y = event.clientY - rect.top - rect.height / 2 - before.y * transform.scale;
    dirtyRef.current = true;
  };

  const handleKeyDown = (event) => {
    const transform = transformRef.current;
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      transform.x += event.key === "ArrowLeft" ? -20 : 20;
      event.preventDefault();
    }
    if (event.key === "ArrowUp" || event.key === "ArrowDown") {
      transform.y += event.key === "ArrowUp" ? -20 : 20;
      event.preventDefault();
    }
    if (event.key === "+" || event.key === "=" || event.key === "-") {
      transform.scale = clamp(transform.scale * (event.key === "-" ? 0.9 : 1.1), 0.45, 2.6);
      event.preventDefault();
    }
    dirtyRef.current = true;
  };

  return (
    <canvas
      ref={canvasRef}
      className="h-[420px] w-full cursor-grab touch-none rounded-[22px] bg-white/15 outline-none active:cursor-grabbing focus-visible:ring-1 focus-visible:ring-black/25 md:h-[520px]"
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={stopInteraction}
      onPointerCancel={stopInteraction}
      onPointerLeave={(event) => {
        if (!interactionRef.current.mode) {
          if (interactionRef.current.hover !== -1) {
            interactionRef.current.hover = -1;
            dirtyRef.current = true;
          }
        } else {
          stopInteraction(event);
        }
      }}
      onWheel={handleWheel}
      onDoubleClick={() => {
        transformRef.current = { x: 0, y: 0, scale: 1 };
        dirtyRef.current = true;
      }}
      onKeyDown={handleKeyDown}
      aria-label="Interactive Obsidian brain graph"
      role="img"
      tabIndex={0}
    />
  );
}
