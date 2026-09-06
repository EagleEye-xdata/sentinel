import React, { useLayoutEffect, useRef } from "react";
import { gsap, ANIM_DURATIONS, ANIM_EASINGS } from "../motion/gsap";
import { useAnimation } from "../motion/AnimationContext";

export function PageTransition({
  pageKey,
  children,
}: {
  pageKey: string;
  children: React.ReactNode;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const { reducedMotion, setRouteSceneState } = useAnimation();

  useLayoutEffect(() => {
    // Notify 3D scene of the active page for smooth camera/lighting interpolation
    setRouteSceneState(pageKey);

    if (reducedMotion || !containerRef.current) return;

    // Scoped GSAP context for safe cleanup
    const ctx = gsap.context(() => {
      gsap.fromTo(
        containerRef.current,
        {
          opacity: 0,
          y: 18,
          filter: "blur(4px)",
        },
        {
          opacity: 1,
          y: 0,
          filter: "blur(0px)",
          duration: ANIM_DURATIONS.normal,
          ease: ANIM_EASINGS.cinematic,
          clearProps: "filter",
        }
      );
    }, containerRef);

    return () => {
      ctx.revert(); // Clean up all GSAP tweens and timelines
    };
  }, [pageKey, reducedMotion, setRouteSceneState]);

  return (
    <div ref={containerRef} style={{ width: "100%", position: "relative" }}>
      {children}
    </div>
  );
}
