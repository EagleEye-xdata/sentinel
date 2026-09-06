import React, { useEffect, useRef } from "react";
import Lenis from "lenis";
import { gsap, ScrollTrigger } from "./gsap";
import { useAnimation } from "./AnimationContext";

export function SmoothScroll({ children }: { children: React.ReactNode }) {
  const { reducedMotion, scrollRef } = useAnimation();
  const lenisRef = useRef<Lenis | null>(null);

  useEffect(() => {
    if (reducedMotion || typeof window === "undefined") {
      return;
    }

    // Initialize high-performance smooth scrolling with Lenis
    const lenis = new Lenis({
      duration: 1.15,
      easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)), // Exponential easeOut
      touchMultiplier: 1.2,
      wheelMultiplier: 1.0,
      infinite: false,
    });

    lenisRef.current = lenis;

    // Synchronize Lenis with GSAP ScrollTrigger
    lenis.on("scroll", (e: any) => {
      ScrollTrigger.update();
      if (scrollRef) {
        scrollRef.current.progress = e.progress || 0;
        scrollRef.current.velocity = e.velocity || 0;
      }
    });

    // Use GSAP ticker to drive Lenis RAF seamlessly
    const tickerCallback = (time: number) => {
      lenis.raf(time * 1000);
    };

    gsap.ticker.add(tickerCallback);
    gsap.ticker.lagSmoothing(0);

    return () => {
      gsap.ticker.remove(tickerCallback);
      lenis.destroy();
      lenisRef.current = null;
    };
  }, [reducedMotion, scrollRef]);

  return <>{children}</>;
}
