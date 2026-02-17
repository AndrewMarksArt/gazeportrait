"use client";

import { useRef, useEffect } from "react";

// ── config ──────────────────────────────────────────
const ATLAS_SRC = "/atlas.jpg";  // path to your sprite atlas
const COLS      = 7;             // columns in the grid
const ROWS      = 7;             // rows in the grid
const FRAME_W   = 256;           // single frame width in px
const FRAME_H   = 256;           // single frame height in px
const INVERT    = false;         // true if gaze tracks opposite to cursor
// ────────────────────────────────────────────────────

const TOTAL = COLS * ROWS;

export default function GazePortrait() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mouse = useRef(0.5);
  const smooth = useRef(0.5);
  const raf = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    canvas.width = FRAME_W;
    canvas.height = FRAME_H;
    ctx.imageSmoothingEnabled = false;

    const atlas = new Image();
    atlas.src = ATLAS_SRC;
    atlas.onerror = () => { /* atlas failed to load — canvas stays blank */ };

    atlas.onload = () => {
      /* draw center frame immediately */
      const mid = Math.floor(TOTAL / 2);
      const midCol = mid % COLS;
      const midRow = Math.floor(mid / COLS);
      ctx.drawImage(atlas, midCol * FRAME_W, midRow * FRAME_H, FRAME_W, FRAME_H, 0, 0, FRAME_W, FRAME_H);

      let lastIdx = mid;
      const t0 = performance.now();

      const draw = (now: number) => {
        /* single smooth — fast response, slight ease */
        smooth.current += (mouse.current - smooth.current) * 0.35;
        /* subtle idle drift so the head never fully stops */
        const drift = Math.sin((now - t0) / 3000) * 0.015;
        const val = Math.max(0, Math.min(1, smooth.current + drift));
        const idx = Math.round(val * (TOTAL - 1));

        /* only redraw when the frame actually changes — crisp, no ghosting */
        if (idx !== lastIdx) {
          lastIdx = idx;
          const col = idx % COLS;
          const row = Math.floor(idx / COLS);
          ctx.drawImage(atlas, col * FRAME_W, row * FRAME_H, FRAME_W, FRAME_H, 0, 0, FRAME_W, FRAME_H);
        }

        raf.current = requestAnimationFrame(draw);
      };
      raf.current = requestAnimationFrame(draw);
    };

    const remap = (px: number) => { const v = px / innerWidth; return INVERT ? 1 - v : v; };
    const onMove = (e: MouseEvent) => { mouse.current = remap(e.clientX); };
    const onTouch = (e: TouchEvent) => { if (e.touches[0]) mouse.current = remap(e.touches[0].clientX); };
    const onLeave = () => { mouse.current = 0.5; };

    addEventListener("mousemove", onMove, { passive: true });
    addEventListener("touchmove", onTouch, { passive: true });
    addEventListener("mouseleave", onLeave, { passive: true });

    return () => {
      cancelAnimationFrame(raf.current);
      removeEventListener("mousemove", onMove);
      removeEventListener("touchmove", onTouch);
      removeEventListener("mouseleave", onLeave);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{ imageRendering: "pixelated", width: 320, height: 320 }}
    />
  );
}
