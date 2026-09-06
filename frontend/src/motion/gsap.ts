import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

// Register ScrollTrigger once globally
if (typeof window !== "undefined") {
  gsap.registerPlugin(ScrollTrigger);
}

export { gsap, ScrollTrigger };

export const ANIM_DURATIONS = {
  fast: 0.15,
  quick: 0.25,
  normal: 0.45,
  smooth: 0.7,
  cinematic: 1.2,
  ambient: 3.0,
};

export const ANIM_EASINGS = {
  smooth: "power2.out",
  cinematic: "power3.out",
  expo: "expo.out",
  soft: "sine.inOut",
  elastic: "back.out(1.4)",
};

/**
 * Animate numbers counting up smoothly
 */
export function animateCounter(
  target: HTMLElement | null,
  endValue: number,
  options: {
    duration?: number;
    prefix?: string;
    suffix?: string;
    decimals?: number;
    delay?: number;
  } = {}
) {
  if (!target) return;
  const {
    duration = ANIM_DURATIONS.cinematic,
    prefix = "",
    suffix = "",
    decimals = 0,
    delay = 0,
  } = options;

  const obj = { val: 0 };
  gsap.to(obj, {
    val: endValue,
    duration,
    delay,
    ease: "power2.out",
    onUpdate: () => {
      if (target) {
        target.textContent = `${prefix}${obj.val.toFixed(decimals)}${suffix}`;
      }
    },
  });
}

/**
 * Reusable Section reveal with ScrollTrigger
 */
export function createSectionReveal(element: HTMLElement | null, trigger?: HTMLElement | null) {
  if (!element) return null;

  return gsap.fromTo(
    element,
    {
      opacity: 0,
      y: 35,
      scale: 0.985,
    },
    {
      opacity: 1,
      y: 0,
      scale: 1,
      duration: ANIM_DURATIONS.smooth,
      ease: ANIM_EASINGS.cinematic,
      scrollTrigger: {
        trigger: trigger || element,
        start: "top 88%",
        toggleActions: "play none none none",
        once: true,
      },
    }
  );
}
