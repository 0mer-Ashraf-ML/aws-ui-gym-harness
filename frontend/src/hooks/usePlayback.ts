/**
 * Hook for managing auto-playback of completed iterations
 */

import { useState, useEffect, useCallback, useRef } from "react";
import type { ActionEntry, PlaybackState, PlaybackControls } from "../types";

interface UsePlaybackOptions {
  autoStart?: boolean;
  defaultSpeed?: number;
  onComplete?: () => void;
}

interface UsePlaybackReturn extends PlaybackState {
  currentAction: ActionEntry | undefined;
  controls: PlaybackControls;
  progress: {
    current: number;
    total: number;
    percentage: number;
  };
}

export const usePlayback = (
  actions: ActionEntry[],
  iterationStatus: string | undefined,
  options: UsePlaybackOptions = {}
): UsePlaybackReturn => {
  const { autoStart = true, defaultSpeed = 1, onComplete } = options;

  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState(defaultSpeed); // 0.5, 1, 2, 4
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Check if iteration is completed (eligible for playback)
  const isCompleted =
    iterationStatus && !["pending", "executing"].includes(iterationStatus);

  // Auto-start playback for completed iterations
  useEffect(() => {
    if (autoStart && isCompleted && actions.length > 0 && currentIndex === 0) {
      setIsPlaying(true);
    }
  }, [autoStart, isCompleted, actions.length, currentIndex]);

  // Playback interval
  useEffect(() => {
    if (!isPlaying || actions.length === 0) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }

    // Calculate interval based on speed (base: 2.5 seconds at 1x)
    const baseInterval = 2500;
    const interval = baseInterval / speed;

    intervalRef.current = setInterval(() => {
      setCurrentIndex((prev) => {
        const next = prev + 1;
        
        if (next >= actions.length) {
          // Reached end, stop playback
          setIsPlaying(false);
          onComplete?.();
          return prev; // Stay at last action
        }
        
        return next;
      });
    }, interval);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [isPlaying, actions.length, speed, onComplete]);

  // Playback controls
  const play = useCallback(() => {
    if (actions.length === 0) return;
    
    // If at end, restart from beginning
    if (currentIndex >= actions.length - 1) {
      setCurrentIndex(0);
    }
    
    setIsPlaying(true);
  }, [actions.length, currentIndex]);

  const pause = useCallback(() => {
    setIsPlaying(false);
  }, []);

  const next = useCallback(() => {
    setCurrentIndex((prev) => Math.min(prev + 1, actions.length - 1));
  }, [actions.length]);

  const previous = useCallback(() => {
    setCurrentIndex((prev) => Math.max(prev - 1, 0));
  }, []);

  const changeSpeed = useCallback((newSpeed: number) => {
    setSpeed(newSpeed);
  }, []);

  const jumpTo = useCallback((index: number) => {
    setCurrentIndex(Math.max(0, Math.min(index, actions.length - 1)));
  }, [actions.length]);

  const controls: PlaybackControls = {
    play,
    pause,
    next,
    previous,
    setSpeed: changeSpeed,
    jumpTo,
  };

  const progress = {
    current: currentIndex + 1,
    total: actions.length,
    percentage: actions.length > 0 ? ((currentIndex + 1) / actions.length) * 100 : 0,
  };

  return {
    currentIndex,
    isPlaying,
    speed,
    currentAction: actions[currentIndex],
    controls,
    progress,
  };
};

