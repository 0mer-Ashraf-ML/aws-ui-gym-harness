import { useState, useEffect, useRef } from "react";

interface UseStickyHeaderOptions {
  threshold?: number;
}

export function useStickyHeader(options: UseStickyHeaderOptions = {}) {
  const { threshold = 200 } = options;
  const [isScrolled, setIsScrolled] = useState(false);
  const headerRef = useRef<HTMLDivElement>(null);
  const stickyHeaderRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleScroll = () => {
      const scrollY = window.scrollY || window.pageYOffset;
      setIsScrolled(scrollY > threshold);
    };

    // Initial check
    handleScroll();

    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, [threshold]);

  return {
    isScrolled,
    headerRef,
    stickyHeaderRef,
  };
}

