import { Pause, Play, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

const POINT_COUNT = 118;
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

const hexToRgb = (hex) => {
  const value = Number.parseInt(hex.replace("#", ""), 16);
  return {
    r: (value >> 16) & 255,
    g: (value >> 8) & 255,
    b: value & 255,
  };
};

function buildOrbGeometry() {
  const points = Array.from({ length: POINT_COUNT }, (_, index) => {
    const y = 1 - (index / (POINT_COUNT - 1)) * 2;
    const radius = Math.sqrt(1 - y * y);
    const angle = GOLDEN_ANGLE * index;
    return {
      x: Math.cos(angle) * radius,
      y,
      z: Math.sin(angle) * radius,
    };
  });

  const edgeKeys = new Set();
  const edges = [];
  points.forEach((point, index) => {
    points
      .map((candidate, candidateIndex) => ({
        candidateIndex,
        distance:
          (point.x - candidate.x) ** 2 +
          (point.y - candidate.y) ** 2 +
          (point.z - candidate.z) ** 2,
      }))
      .filter(({ candidateIndex }) => candidateIndex !== index)
      .sort((a, b) => a.distance - b.distance)
      .slice(0, 4)
      .forEach(({ candidateIndex }) => {
        const a = Math.min(index, candidateIndex);
        const b = Math.max(index, candidateIndex);
        const key = `${a}:${b}`;
        if (!edgeKeys.has(key)) {
          edgeKeys.add(key);
          edges.push([a, b]);
        }
      });
  });

  return { points, edges };
}

export function WireframeOrb({ accent }) {
  const canvasRef = useRef(null);
  const wrapperRef = useRef(null);
  const frameRef = useRef(null);
  const rotationRef = useRef({ x: -0.18, y: 0.45 });
  const dragRef = useRef({ active: false, x: 0, y: 0 });
  const [visible, setVisible] = useState(false);
  const [playing, setPlaying] = useState(
    () => typeof window === "undefined" || !window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const geometry = useMemo(buildOrbGeometry, []);

  useEffect(() => {
    const wrapper = wrapperRef.current;
    if (!wrapper) return undefined;
    const observer = new IntersectionObserver(
      ([entry]) => {
        setVisible(entry.isIntersecting);
      },
      { threshold: 0.05 },
    );
    observer.observe(wrapper);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !visible) return undefined;
    const context = canvas.getContext("2d");
    const color = hexToRgb(accent);
    let previousTime = performance.now();

    const draw = (time) => {
      const rect = canvas.getBoundingClientRect();
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 1.5);
      const width = Math.max(1, Math.round(rect.width * pixelRatio));
      const height = Math.max(1, Math.round(rect.height * pixelRatio));
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }

      const elapsed = Math.min(32, time - previousTime);
      previousTime = time;
      if (playing && !dragRef.current.active) {
        rotationRef.current.y += elapsed * 0.00018;
      }

      context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
      context.clearRect(0, 0, rect.width, rect.height);

      const centerX = rect.width / 2;
      const centerY = rect.height / 2;
      const radius = Math.min(rect.width, rect.height) * 0.62;
      const { x: rotateX, y: rotateY } = rotationRef.current;
      const cosX = Math.cos(rotateX);
      const sinX = Math.sin(rotateX);
      const cosY = Math.cos(rotateY);
      const sinY = Math.sin(rotateY);

      const projected = geometry.points.map((point) => {
        const x1 = point.x * cosY - point.z * sinY;
        const z1 = point.x * sinY + point.z * cosY;
        const y1 = point.y * cosX - z1 * sinX;
        const z2 = point.y * sinX + z1 * cosX;
        const perspective = 1 / (1.35 - z2 * 0.18);
        return {
          x: centerX + x1 * radius * perspective,
          y: centerY + y1 * radius * perspective,
          z: z2,
        };
      });

      context.lineWidth = 0.75;
      geometry.edges.forEach(([from, to]) => {
        const a = projected[from];
        const b = projected[to];
        const depth = clamp(((a.z + b.z) / 2 + 1) / 2, 0, 1);
        context.strokeStyle = `rgba(${color.r}, ${color.g}, ${color.b}, ${0.09 + depth * 0.28})`;
        context.beginPath();
        context.moveTo(a.x, a.y);
        context.lineTo(b.x, b.y);
        context.stroke();
      });

      projected
        .slice()
        .sort((a, b) => a.z - b.z)
        .forEach((point) => {
          const depth = clamp((point.z + 1) / 2, 0, 1);
          context.shadowBlur = depth > 0.62 ? 8 : 0;
          context.shadowColor = `rgba(${color.r}, ${color.g}, ${color.b}, 0.8)`;
          context.fillStyle = `rgba(245, 245, 242, ${0.28 + depth * 0.72})`;
          context.beginPath();
          context.arc(point.x, point.y, 0.7 + depth * 1.7, 0, Math.PI * 2);
          context.fill();
        });
      context.shadowBlur = 0;

      frameRef.current = requestAnimationFrame(draw);
    };

    frameRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frameRef.current);
  }, [accent, geometry, playing, visible]);

  const handlePointerDown = (event) => {
    dragRef.current = { active: true, x: event.clientX, y: event.clientY };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handlePointerMove = (event) => {
    if (!dragRef.current.active) return;
    const deltaX = event.clientX - dragRef.current.x;
    const deltaY = event.clientY - dragRef.current.y;
    rotationRef.current.y += deltaX * 0.008;
    rotationRef.current.x = clamp(rotationRef.current.x + deltaY * 0.008, -1.2, 1.2);
    dragRef.current.x = event.clientX;
    dragRef.current.y = event.clientY;
  };

  const stopDragging = (event) => {
    dragRef.current.active = false;
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };

  const handleKeyDown = (event) => {
    const distance = event.shiftKey ? 0.24 : 0.1;
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      rotationRef.current.y += event.key === "ArrowLeft" ? -distance : distance;
      event.preventDefault();
    }
    if (event.key === "ArrowUp" || event.key === "ArrowDown") {
      rotationRef.current.x = clamp(
        rotationRef.current.x + (event.key === "ArrowUp" ? -distance : distance),
        -1.2,
        1.2,
      );
      event.preventDefault();
    }
  };

  return (
    <div
      ref={wrapperRef}
      className="orb-shell relative flex h-full min-h-[430px] w-full flex-col items-center justify-center overflow-hidden rounded-[34px]"
      style={{
        "--orb-accent": accent,
        background: `radial-gradient(circle at 50% 50%, ${accent}16, transparent 62%)`,
      }}
    >
      <canvas
        ref={canvasRef}
        className="h-[min(58vh,560px)] w-full cursor-grab touch-none rounded-[28px] outline-none active:cursor-grabbing focus-visible:ring-1 focus-visible:ring-white/30"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={stopDragging}
        onPointerCancel={stopDragging}
        onKeyDown={handleKeyDown}
        tabIndex={0}
        aria-label="Interactive Spencer wireframe orb. Drag or use arrow keys to rotate."
        role="img"
      />

      <div className="absolute bottom-5 flex items-center gap-2">
        <button
          type="button"
          onClick={() => setPlaying((value) => !value)}
          className="orb-control"
          aria-label={playing ? "Pause orb rotation" : "Play orb rotation"}
        >
          {playing ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
          {playing ? "Pause" : "Play"}
        </button>
        <button
          type="button"
          onClick={() => {
            rotationRef.current = { x: -0.18, y: 0.45 };
          }}
          className="orb-control"
          aria-label="Reset orb rotation"
        >
          <RotateCcw className="h-3.5 w-3.5" />
          Reset
        </button>
      </div>

      <p className="pointer-events-none absolute top-5 font-mono text-[9px] uppercase tracking-[0.2em] text-white/28">
        Drag to rotate
      </p>
    </div>
  );
}
