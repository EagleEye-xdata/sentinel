import React, {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  useCallback,
} from "react";

export type QualityLevel = "HIGH" | "MEDIUM" | "LOW";

export interface SceneParameters {
  coreVisible: boolean;
  coreScale: number;
  coreIntensity: number;
  networkActivity: number;
  particleDensity: number;
  scanSpeed: number;
  redLightIntensity: number;
  cameraPos: [number, number, number];
  cameraTarget: [number, number, number];
}

export interface AnimationContextValue {
  quality: QualityLevel;
  reducedMotion: boolean;
  mouseRef: React.MutableRefObject<{ x: number; y: number; targetX: number; targetY: number }>;
  sceneParamsRef: React.MutableRefObject<SceneParameters>;
  scrollRef: React.MutableRefObject<{ progress: number; velocity: number }>;
  triggerThreatPulse: () => void;
  triggerScanSweep: () => void;
  pulseTrigger: number;
  scanTrigger: number;
  setRouteSceneState: (pageName: string) => void;
}

const DEFAULT_PARAMS: SceneParameters = {
  coreVisible: true,
  coreScale: 1.0,
  coreIntensity: 1.0,
  networkActivity: 0.6,
  particleDensity: 1.0,
  scanSpeed: 1.0,
  redLightIntensity: 0.8,
  cameraPos: [0, 0, 7.5],
  cameraTarget: [0, 0, 0],
};

const ROUTE_CONFIGS: Record<string, Partial<SceneParameters>> = {
  Overview: {
    coreVisible: true,
    coreScale: 1.0,
    coreIntensity: 1.1,
    networkActivity: 0.7,
    scanSpeed: 1.0,
    redLightIntensity: 0.85,
    cameraPos: [0.6, 0.1, 7.2],
    cameraTarget: [0.4, 0, 0],
  },
  Targets: {
    coreVisible: false,
    coreScale: 0.6,
    coreIntensity: 0.4,
    networkActivity: 1.2,
    scanSpeed: 0.8,
    redLightIntensity: 0.6,
    cameraPos: [-0.4, 0.4, 8.5],
    cameraTarget: [0, 0, 0],
  },
  "Attack Library": {
    coreVisible: false,
    coreScale: 0.5,
    coreIntensity: 0.6,
    networkActivity: 0.9,
    scanSpeed: 1.4,
    redLightIntensity: 1.3,
    cameraPos: [0, -0.3, 8.0],
    cameraTarget: [0, 0, 0],
  },
  "Payload Lab": {
    coreVisible: false,
    coreScale: 0.5,
    coreIntensity: 0.5,
    networkActivity: 0.8,
    scanSpeed: 1.1,
    redLightIntensity: 0.9,
    cameraPos: [0.5, 0.2, 8.0],
    cameraTarget: [0, 0, 0],
  },
  "Run Test": {
    coreVisible: true,
    coreScale: 0.85,
    coreIntensity: 1.2,
    networkActivity: 1.1,
    scanSpeed: 1.3,
    redLightIntensity: 1.2,
    cameraPos: [1.2, 0.2, 7.8],
    cameraTarget: [0.3, 0, 0],
  },
  "Live Console": {
    coreVisible: false,
    coreScale: 0.4,
    coreIntensity: 0.7,
    networkActivity: 1.4,
    scanSpeed: 1.8,
    redLightIntensity: 1.4,
    cameraPos: [0, 0, 8.5],
    cameraTarget: [0, 0, 0],
  },
  "Run Monitor": {
    coreVisible: false,
    coreScale: 0.6,
    coreIntensity: 0.9,
    networkActivity: 1.3,
    scanSpeed: 1.5,
    redLightIntensity: 1.1,
    cameraPos: [-0.6, 0.1, 8.2],
    cameraTarget: [0, 0, 0],
  },
  Alerts: {
    coreVisible: false,
    coreScale: 0.4,
    coreIntensity: 0.6,
    networkActivity: 1.0,
    scanSpeed: 1.6,
    redLightIntensity: 1.8,
    cameraPos: [0, 0.5, 8.0],
    cameraTarget: [0, 0, 0],
  },
  Reports: {
    coreVisible: false,
    coreScale: 0.3,
    coreIntensity: 0.3,
    networkActivity: 0.4,
    scanSpeed: 0.5,
    redLightIntensity: 0.4,
    cameraPos: [0, 0, 9.0],
    cameraTarget: [0, 0, 0],
  },
  Inspect: {
    coreVisible: false,
    coreScale: 0.5,
    coreIntensity: 0.6,
    networkActivity: 0.8,
    scanSpeed: 0.9,
    redLightIntensity: 0.7,
    cameraPos: [0.4, -0.2, 8.4],
    cameraTarget: [0, 0, 0],
  },
  Settings: {
    coreVisible: false,
    coreScale: 0.3,
    coreIntensity: 0.3,
    networkActivity: 0.3,
    scanSpeed: 0.4,
    redLightIntensity: 0.3,
    cameraPos: [0, 0, 9.2],
    cameraTarget: [0, 0, 0],
  },
};

const AnimationContext = createContext<AnimationContextValue | null>(null);

export function AnimationProvider({ children }: { children: React.ReactNode }) {
  const [quality, setQuality] = useState<QualityLevel>("HIGH");
  const [reducedMotion, setReducedMotion] = useState(false);
  const [pulseTrigger, setPulseTrigger] = useState(0);
  const [scanTrigger, setScanTrigger] = useState(0);

  const mouseRef = useRef({ x: 0, y: 0, targetX: 0, targetY: 0 });
  const sceneParamsRef = useRef<SceneParameters>({ ...DEFAULT_PARAMS });
  const scrollRef = useRef({ progress: 0, velocity: 0 });

  // Detect quality and reduced motion on mount
  useEffect(() => {
    // 1. Reduced motion check
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReducedMotion(mediaQuery.matches);
    const motionListener = (e: MediaQueryListEvent) => setReducedMotion(e.matches);
    mediaQuery.addEventListener("change", motionListener);

    // 2. Adaptive Quality check
    const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent) || window.innerWidth < 768;
    const isTablet = window.innerWidth >= 768 && window.innerWidth < 1024;
    const hardwareConcurrency = navigator.hardwareConcurrency || 4;

    if (isMobile || hardwareConcurrency <= 2) {
      setQuality("LOW");
    } else if (isTablet || hardwareConcurrency <= 4) {
      setQuality("MEDIUM");
    } else {
      setQuality("HIGH");
    }

    // 3. Normalized mouse listener with zero React state overhead
    const handleMouseMove = (e: MouseEvent) => {
      // Map to -1 to +1 range
      mouseRef.current.targetX = (e.clientX / window.innerWidth) * 2 - 1;
      mouseRef.current.targetY = -(e.clientY / window.innerHeight) * 2 + 1;
    };

    window.addEventListener("mousemove", handleMouseMove, { passive: true });

    return () => {
      mediaQuery.removeEventListener("change", motionListener);
      window.removeEventListener("mousemove", handleMouseMove);
    };
  }, []);

  const triggerThreatPulse = useCallback(() => {
    setPulseTrigger((prev) => prev + 1);
  }, []);

  const triggerScanSweep = useCallback(() => {
    setScanTrigger((prev) => prev + 1);
  }, []);

  const setRouteSceneState = useCallback((pageName: string) => {
    const config = ROUTE_CONFIGS[pageName] || DEFAULT_PARAMS;
    // Smoothly update target scene parameters without forcing a React render
    const cur = sceneParamsRef.current;
    Object.assign(cur, config);
  }, []);

  return (
    <AnimationContext.Provider
      value={{
        quality,
        reducedMotion,
        mouseRef,
        sceneParamsRef,
        scrollRef,
        triggerThreatPulse,
        triggerScanSweep,
        pulseTrigger,
        scanTrigger,
        setRouteSceneState,
      }}
    >
      {children}
    </AnimationContext.Provider>
  );
}

export function useAnimation() {
  const ctx = useContext(AnimationContext);
  if (!ctx) {
    throw new Error("useAnimation must be used within an AnimationProvider");
  }
  return ctx;
}
