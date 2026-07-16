'use client';

import React, { useRef, useEffect, useCallback, useState, ReactNode } from 'react';
import { gsap } from 'gsap';
import { useTheme } from 'next-themes';

const DEFAULT_PARTICLE_COUNT = 12;
const DEFAULT_SPOTLIGHT_RADIUS = 300;
const DEFAULT_GLOW_COLOR = '0, 213, 255';

interface CardDataItem {
  color: string;
  title: string;
  description: string;
  label: string;
}

const cardData: CardDataItem[] = [
  {
    color: '#120F17',
    title: 'Analytics',
    description: 'Track user behavior',
    label: 'Insights'
  },
  {
    color: '#120F17',
    title: 'Dashboard',
    description: 'Centralized data view',
    label: 'Overview'
  },
  {
    color: '#120F17',
    title: 'Collaboration',
    description: 'Work together seamlessly',
    label: 'Teamwork'
  },
  {
    color: '#120F17',
    title: 'Automation',
    description: 'Streamline workflows',
    label: 'Efficiency'
  },
  {
    color: '#120F17',
    title: 'Integration',
    description: 'Connect favorite tools',
    label: 'Connectivity'
  },
  {
    color: '#120F17',
    title: 'Security',
    description: 'Enterprise-grade protection',
    label: 'Protection'
  }
];

const createParticleElement = (x: number, y: number, color: string = DEFAULT_GLOW_COLOR) => {
  const el = document.createElement('div');
  el.className = 'particle';
  el.style.cssText = `
    position: absolute;
    width: 4px;
    height: 4px;
    border-radius: 50%;
    background: rgba(${color}, 1);
    box-shadow: 0 0 6px rgba(${color}, 0.6);
    pointer-events: none;
    z-index: 100;
    left: ${x}px;
    top: ${y}px;
  `;
  return el;
};

const calculateSpotlightValues = (radius: number) => ({
  proximity: radius * 0.5,
  fadeDistance: radius * 0.75
});

const getCardGridStyle = (index: number, cols: number): React.CSSProperties => {
  if (cols !== 4) return {};
  
  switch (index) {
    case 2: // 3rd card
      return {
        gridColumn: 'span 2',
        gridRow: 'span 2'
      };
    case 3: // 4th card
      return {
        gridColumn: '1 / span 2',
        gridRow: '2 / span 2'
      };
    case 5: // 6th card
      return {
        gridColumn: '4',
        gridRow: '3'
      };
    default:
      return {};
  }
};

const getCardBaseStyle = (cardColor: string, index: number, cols: number): React.CSSProperties => {
  const gridStyle = getCardGridStyle(index, cols);
  return {
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'space-between',
    position: 'relative',
    aspectRatio: '4/3',
    minHeight: cols === 1 ? '180px' : '200px',
    width: '100%',
    padding: '1.25em',
    borderRadius: '20px',
    border: '1px solid #93d5e8ff',
    backgroundColor: cardColor,
    fontWeight: 300,
    overflow: 'hidden',
    transition: 'transform 0.3s ease, box-shadow 0.3s ease',
    ...gridStyle
  };
};

const useWindowWidth = () => {
  const [width, setWidth] = useState(1200);

  useEffect(() => {
    const handleResize = () => setWidth(window.innerWidth);
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return width;
};

interface ParticleCardProps {
  children: ReactNode;
  index: number;
  cols: number;
  disableAnimations?: boolean;
  cardColor: string;
  particleCount?: number;
  glowColor?: string;
  enableTilt?: boolean;
  clickEffect?: boolean;
  enableMagnetism?: boolean;
  enableBorderGlow?: boolean;
}

const ParticleCard = ({
  children,
  index,
  cols,
  disableAnimations = false,
  cardColor,
  particleCount = DEFAULT_PARTICLE_COUNT,
  glowColor = DEFAULT_GLOW_COLOR,
  enableTilt = true,
  clickEffect = false,
  enableMagnetism = false,
  enableBorderGlow = true
}: ParticleCardProps) => {
  const cardRef = useRef<HTMLDivElement>(null);
  const particlesRef = useRef<HTMLDivElement[]>([]);
  const timeoutsRef = useRef<NodeJS.Timeout[]>([]);
  const isHoveredRef = useRef(false);
  const memoizedParticles = useRef<HTMLDivElement[]>([]);
  const particlesInitialized = useRef(false);
  const magnetismAnimationRef = useRef<gsap.core.Tween | null>(null);
  
  const [isHoveredState, setIsHoveredState] = useState(false);

  const initializeParticles = useCallback(() => {
    if (particlesInitialized.current || !cardRef.current) return;

    const { width, height } = cardRef.current.getBoundingClientRect();
    memoizedParticles.current = Array.from({ length: particleCount }, () =>
      createParticleElement(Math.random() * width, Math.random() * height, glowColor)
    ) as HTMLDivElement[];
    particlesInitialized.current = true;
  }, [particleCount, glowColor]);

  const clearAllParticles = useCallback(() => {
    timeoutsRef.current.forEach(clearTimeout);
    timeoutsRef.current = [];
    magnetismAnimationRef.current?.kill();

    particlesRef.current.forEach(particle => {
      gsap.to(particle, {
        scale: 0,
        opacity: 0,
        duration: 0.3,
        ease: 'back.in(1.7)',
        onComplete: () => {
          particle.parentNode?.removeChild(particle);
        }
      });
    });
    particlesRef.current = [];
  }, []);

  const animateParticles = useCallback(() => {
    if (!cardRef.current || !isHoveredRef.current) return;

    if (!particlesInitialized.current) {
      initializeParticles();
    }

    memoizedParticles.current.forEach((particle, index) => {
      const timeoutId = setTimeout(() => {
        if (!isHoveredRef.current || !cardRef.current) return;

        const clone = particle.cloneNode(true) as HTMLDivElement;
        cardRef.current.appendChild(clone);
        particlesRef.current.push(clone);

        gsap.fromTo(clone, { scale: 0, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.3, ease: 'back.out(1.7)' });

        gsap.to(clone, {
          x: (Math.random() - 0.5) * 100,
          y: (Math.random() - 0.5) * 100,
          rotation: Math.random() * 360,
          duration: 2 + Math.random() * 2,
          ease: 'none',
          repeat: -1,
          yoyo: true
        });

        gsap.to(clone, {
          opacity: 0.3,
          duration: 1.5,
          ease: 'power2.inOut',
          repeat: -1,
          yoyo: true
        });
      }, index * 100);

      timeoutsRef.current.push(timeoutId);
    });
  }, [initializeParticles]);

  const handleMouseEnter = () => {
    setIsHoveredState(true);
    if (disableAnimations) return;
    isHoveredRef.current = true;
    animateParticles();

    if (enableTilt && cardRef.current) {
      gsap.to(cardRef.current, {
        rotateX: 5,
        rotateY: 5,
        duration: 0.3,
        ease: 'power2.out',
        transformPerspective: 1000
      });
    }
  };

  const handleMouseLeave = () => {
    setIsHoveredState(false);
    if (disableAnimations) return;
    isHoveredRef.current = false;
    clearAllParticles();

    if (enableTilt && cardRef.current) {
      gsap.to(cardRef.current, {
        rotateX: 0,
        rotateY: 0,
        duration: 0.3,
        ease: 'power2.out'
      });
    }

    if (enableMagnetism && cardRef.current) {
      gsap.to(cardRef.current, {
        x: 0,
        y: 0,
        duration: 0.3,
        ease: 'power2.out'
      });
    }

    const borderGlowEl = cardRef.current?.querySelector<HTMLElement>('.border-glow');
    if (borderGlowEl) {
      borderGlowEl.style.opacity = '0';
    }
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (disableAnimations) return;
    if (!enableTilt && !enableMagnetism) return;
    if (!cardRef.current) return;

    const element = cardRef.current;
    const rect = element.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;

    if (enableTilt) {
      const rotateX = ((y - centerY) / centerY) * -10;
      const rotateY = ((x - centerX) / centerX) * 10;

      gsap.to(element, {
        rotateX,
        rotateY,
        duration: 0.1,
        ease: 'power2.out',
        transformPerspective: 1000
      });
    }

    if (enableMagnetism) {
      const magnetX = (x - centerX) * 0.05;
      const magnetY = (y - centerY) * 0.05;

      magnetismAnimationRef.current = gsap.to(element, {
        x: magnetX,
        y: magnetY,
        duration: 0.3,
        ease: 'power2.out'
      });
    }
  };

  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (disableAnimations) return;
    if (!clickEffect || !cardRef.current) return;

    const element = cardRef.current;
    const rect = element.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const maxDistance = Math.max(
      Math.hypot(x, y),
      Math.hypot(x - rect.width, y),
      Math.hypot(x, y - rect.height),
      Math.hypot(x - rect.width, y - rect.height)
    );

    const ripple = document.createElement('div');
    ripple.style.cssText = `
      position: absolute;
      width: ${maxDistance * 2}px;
      height: ${maxDistance * 2}px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(${glowColor}, 0.4) 0%, rgba(${glowColor}, 0.2) 30%, transparent 70%);
      left: ${x - maxDistance}px;
      top: ${y - maxDistance}px;
      pointer-events: none;
      z-index: 1000;
    `;

    element.appendChild(ripple);

    gsap.fromTo(
      ripple,
      {
        scale: 0,
        opacity: 1
      },
      {
        scale: 1,
        opacity: 0,
        duration: 0.8,
        ease: 'power2.out',
        onComplete: () => ripple.remove()
      }
    );
  };

  useEffect(() => {
    return () => {
      isHoveredRef.current = false;
      clearAllParticles();
    };
  }, [clearAllParticles]);

  const baseStyle = getCardBaseStyle(cardColor, index, cols);
  const cardStyle: React.CSSProperties = {
    ...baseStyle,
    transform: isHoveredState && !disableAnimations ? 'translateY(-2px)' : 'translateY(0)',
    boxShadow: isHoveredState && !disableAnimations 
      ? '0 8px 25px rgba(0, 0, 0, 0.4), 0 0 30px rgba(0, 213, 255, 0.2)' 
      : 'none'
  };

  return (
    <div
      ref={cardRef}
      className="magic-bento-card"
      style={cardStyle}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onMouseMove={handleMouseMove}
      onClick={handleClick}
    >
      {enableBorderGlow && (
        <div
          className="border-glow"
          style={{
            position: 'absolute',
            inset: 0,
            padding: '1px',
            borderRadius: 'inherit',
            pointerEvents: 'none',
            opacity: 0,
            transition: 'opacity 0.3s ease',
            zIndex: 1,
            WebkitMask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)',
            WebkitMaskComposite: 'xor',
            mask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)',
            maskComposite: 'exclude'
          }}
        />
      )}
      {children}
    </div>
  );
};

interface MagicBentoProps {
  textAutoHide?: boolean;
  enableStars?: boolean;
  enableSpotlight?: boolean;
  enableBorderGlow?: boolean;
  disableAnimations?: boolean;
  spotlightRadius?: number;
  particleCount?: number;
  enableTilt?: boolean;
  glowColor?: string;
  clickEffect?: boolean;
  enableMagnetism?: boolean;
}

export function MagicBento({
  textAutoHide = true,
  enableStars = true,
  enableSpotlight = true,
  enableBorderGlow = true,
  disableAnimations = false,
  spotlightRadius = DEFAULT_SPOTLIGHT_RADIUS,
  particleCount = DEFAULT_PARTICLE_COUNT,
  enableTilt = false,
  glowColor = DEFAULT_GLOW_COLOR,
  clickEffect = true,
  enableMagnetism = true
}: MagicBentoProps) {
  const gridRef = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(false);
  const { resolvedTheme } = useTheme();
  
  const currentGlowColor = glowColor !== DEFAULT_GLOW_COLOR 
    ? glowColor 
    : (resolvedTheme === 'light' ? '14, 206, 240' : '0, 213, 255');

  const windowWidth = useWindowWidth();
  
  const cols = windowWidth < 600 ? 1 : windowWidth < 1024 ? 2 : 4;
  const shouldDisableAnimations = disableAnimations;

  const [hoveredCard, setHoveredCard] = useState<number | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted || shouldDisableAnimations || !gridRef.current || !enableSpotlight) return;

    const spotlight = document.createElement('div');
    spotlight.className = 'global-spotlight';
    spotlight.style.cssText = `
      position: fixed;
      width: 800px;
      height: 800px;
      border-radius: 50%;
      pointer-events: none;
      background: radial-gradient(circle,
        rgba(${currentGlowColor}, 0.15) 0%,
        rgba(${currentGlowColor}, 0.08) 15%,
        rgba(${currentGlowColor}, 0.04) 25%,
        rgba(${currentGlowColor}, 0.02) 40%,
        rgba(${currentGlowColor}, 0.01) 65%,
        transparent 70%
      );
      z-index: 200;
      opacity: 0;
      transform: translate(-50%, -50%);
      mix-blend-mode: screen;
      pointer-events: none;
    `;
    document.body.appendChild(spotlight);

    const handleMouseMove = (e: MouseEvent) => {
      if (!gridRef.current) return;

      const rect = gridRef.current.getBoundingClientRect();
      const mouseInside =
        e.clientX >= rect.left && e.clientX <= rect.right && e.clientY >= rect.top && e.clientY <= rect.bottom;

      const cards = gridRef.current.querySelectorAll<HTMLElement>('.magic-bento-card');

      if (!mouseInside) {
        gsap.to(spotlight, {
          opacity: 0,
          duration: 0.3,
          ease: 'power2.out'
        });
        cards.forEach(card => {
          const borderGlow = card.querySelector<HTMLElement>('.border-glow');
          if (borderGlow) borderGlow.style.opacity = '0';
        });
        return;
      }

      const proximity = spotlightRadius * 0.5;
      const fadeDistance = spotlightRadius * 0.75;
      let minDistance = Infinity;

      cards.forEach(card => {
        const cardElement = card;
        const cardRect = cardElement.getBoundingClientRect();
        const centerX = cardRect.left + cardRect.width / 2;
        const centerY = cardRect.top + cardRect.height / 2;
        const distance =
          Math.hypot(e.clientX - centerX, e.clientY - centerY) - Math.max(cardRect.width, cardRect.height) / 2;
        const effectiveDistance = Math.max(0, distance);

        minDistance = Math.min(minDistance, effectiveDistance);

        let glowIntensity = 0;
        if (effectiveDistance <= proximity) {
          glowIntensity = 1;
        } else if (effectiveDistance <= fadeDistance) {
          glowIntensity = (fadeDistance - effectiveDistance) / (fadeDistance - proximity);
        }

        const x = e.clientX - cardRect.left;
        const y = e.clientY - cardRect.top;

        const borderGlowEl = cardElement.querySelector<HTMLElement>('.border-glow');
        if (borderGlowEl) {
          borderGlowEl.style.background = `radial-gradient(${spotlightRadius}px circle at ${x}px ${y}px, rgba(${currentGlowColor}, ${glowIntensity * 0.8}) 0%, rgba(${currentGlowColor}, ${glowIntensity * 0.4}) 30%, transparent 60%)`;
          borderGlowEl.style.opacity = '1';
        }
      });

      gsap.to(spotlight, {
        left: e.clientX,
        top: e.clientY,
        duration: 0.1,
        ease: 'power2.out'
      });

      const targetOpacity =
        minDistance <= proximity
          ? 0.8
          : minDistance <= fadeDistance
            ? ((fadeDistance - minDistance) / (fadeDistance - proximity)) * 0.8
            : 0;

      gsap.to(spotlight, {
        opacity: targetOpacity,
        duration: targetOpacity > 0 ? 0.2 : 0.5,
        ease: 'power2.out'
      });
    };

    const handleMouseLeave = () => {
      gridRef.current?.querySelectorAll<HTMLElement>('.border-glow').forEach(el => {
        el.style.opacity = '0';
      });
      gsap.to(spotlight, {
        opacity: 0,
        duration: 0.3,
        ease: 'power2.out'
      });
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseleave', handleMouseLeave);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseleave', handleMouseLeave);
      spotlight.parentNode?.removeChild(spotlight);
    };
  }, [mounted, shouldDisableAnimations, enableSpotlight, currentGlowColor, spotlightRadius]);

  const gridStyle: React.CSSProperties = {
    display: 'grid',
    gap: '0.5em',
    padding: '0.75em',
    maxWidth: '54em',
    width: '100%',
    gridTemplateColumns: `repeat(${cols}, 1fr)`,
    position: 'relative',
    userSelect: 'none'
  };

  const headerStyle: React.CSSProperties = {
    display: 'flex',
    position: 'relative',
    color: '#ffffff',
    gap: '0.75em',
    justifyContent: 'space-between',
    zIndex: 2
  };

  const contentStyle: React.CSSProperties = {
    display: 'flex',
    position: 'relative',
    color: '#ffffff',
    flexDirection: 'column',
    zIndex: 2
  };

  const labelStyle: React.CSSProperties = {
    fontSize: '14px',
    color: '#00d5ff',
    fontWeight: 500,
    textTransform: 'uppercase',
    letterSpacing: '0.05em'
  };

  const titleStyle: React.CSSProperties = {
    fontWeight: 500,
    fontSize: '18px',
    margin: '0 0 0.25em',
    color: '#ffffff'
  };

  const descriptionStyle: React.CSSProperties = {
    fontSize: '13px',
    lineHeight: 1.4,
    opacity: 0.8,
    color: '#a0a0b0'
  };

  const textClampTitleStyle: React.CSSProperties = textAutoHide ? {
    ...titleStyle,
    display: '-webkit-box',
    WebkitBoxOrient: 'vertical',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    WebkitLineClamp: 1
  } : titleStyle;

  const textClampDescStyle: React.CSSProperties = textAutoHide ? {
    ...descriptionStyle,
    display: '-webkit-box',
    WebkitBoxOrient: 'vertical',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    WebkitLineClamp: 2
  } : descriptionStyle;

  return (
    <div style={gridStyle} ref={gridRef}>
      {cardData.map((card, index) => {
        const cardProps = {
          index,
          cols,
          cardColor: card.color,
          disableAnimations: shouldDisableAnimations,
          particleCount,
          glowColor,
          enableTilt,
          clickEffect,
          enableMagnetism,
          enableBorderGlow
        };

        if (enableStars) {
          return (
            <ParticleCard key={index} {...cardProps}>
              <div style={headerStyle}>
                <div style={labelStyle}>{card.label}</div>
              </div>
              <div style={contentStyle}>
                <h2 style={textClampTitleStyle}>{card.title}</h2>
                <p style={textClampDescStyle}>{card.description}</p>
              </div>
            </ParticleCard>
          );
        }

        const isHovered = hoveredCard === index;
        const baseStyle = getCardBaseStyle(card.color, index, cols);
        const cardStyle: React.CSSProperties = {
          ...baseStyle,
          transform: isHovered && !shouldDisableAnimations ? 'translateY(-2px)' : 'translateY(0)',
          boxShadow: isHovered && !shouldDisableAnimations 
            ? '0 8px 25px rgba(0, 0, 0, 0.4), 0 0 30px rgba(0, 213, 255, 0.2)' 
            : 'none'
        };

        return (
          <div
            key={index}
            className="magic-bento-card"
            style={cardStyle}
            onMouseEnter={() => setHoveredCard(index)}
            onMouseLeave={() => {
              setHoveredCard(null);
              const borderGlowEl = gridRef.current?.querySelectorAll<HTMLElement>('.magic-bento-card')[index]?.querySelector<HTMLElement>('.border-glow');
              if (borderGlowEl) borderGlowEl.style.opacity = '0';
            }}
            onMouseMove={(e) => {
              if (shouldDisableAnimations) return;
              const rect = e.currentTarget.getBoundingClientRect();
              const x = e.clientX - rect.left;
              const y = e.clientY - rect.top;
              const centerX = rect.width / 2;
              const centerY = rect.height / 2;

              if (enableTilt) {
                const rotateX = ((y - centerY) / centerY) * -10;
                const rotateY = ((x - centerX) / centerX) * 10;
                gsap.to(e.currentTarget, {
                  rotateX,
                  rotateY,
                  duration: 0.1,
                  ease: 'power2.out',
                  transformPerspective: 1000
                });
              }

              if (enableMagnetism) {
                const magnetX = (x - centerX) * 0.05;
                const magnetY = (y - centerY) * 0.05;
                gsap.to(e.currentTarget, {
                  x: magnetX,
                  y: magnetY,
                  duration: 0.3,
                  ease: 'power2.out'
                });
              }
            }}
            onClick={(e) => {
              if (!clickEffect || shouldDisableAnimations) return;
              const rect = e.currentTarget.getBoundingClientRect();
              const x = e.clientX - rect.left;
              const y = e.clientY - rect.top;

              const maxDistance = Math.max(
                Math.hypot(x, y),
                Math.hypot(x - rect.width, y),
                Math.hypot(x, y - rect.height),
                Math.hypot(x - rect.width, y - rect.height)
              );

              const ripple = document.createElement('div');
              ripple.style.cssText = `
                position: absolute;
                width: ${maxDistance * 2}px;
                height: ${maxDistance * 2}px;
                border-radius: 50%;
                background: radial-gradient(circle, rgba(${currentGlowColor}, 0.4) 0%, rgba(${currentGlowColor}, 0.2) 30%, transparent 70%);
                left: ${x - maxDistance}px;
                top: ${y - maxDistance}px;
                pointer-events: none;
                z-index: 1000;
              `;
              e.currentTarget.appendChild(ripple);

              gsap.fromTo(
                ripple,
                {
                  scale: 0,
                  opacity: 1
                },
                {
                  scale: 1,
                  opacity: 0,
                  duration: 0.8,
                  ease: 'power2.out',
                  onComplete: () => ripple.remove()
                }
              );
            }}
          >
            {enableBorderGlow && (
              <div
                className="border-glow"
                style={{
                  position: 'absolute',
                  inset: 0,
                  padding: '1px',
                  borderRadius: 'inherit',
                  pointerEvents: 'none',
                  opacity: 0,
                  transition: 'opacity 0.3s ease',
                  zIndex: 1,
                  WebkitMask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)',
                  WebkitMaskComposite: 'xor',
                  mask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)',
                  maskComposite: 'exclude'
                }}
              />
            )}
            <div style={headerStyle}>
              <div style={labelStyle}>{card.label}</div>
            </div>
            <div style={contentStyle}>
              <h2 style={textClampTitleStyle}>{card.title}</h2>
              <p style={textClampDescStyle}>{card.description}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function MagicBentoCard({
  children,
  className = '',
  style = {},
  glowColor = DEFAULT_GLOW_COLOR,
  enableStars = true,
  enableTilt = true,
  enableMagnetism = true,
  clickEffect = true,
  enableBorderGlow = true,
  particleCount = DEFAULT_PARTICLE_COUNT,
  disableAnimations = false
}: {
  children: ReactNode;
  className?: string;
  style?: React.CSSProperties;
  glowColor?: string;
  enableStars?: boolean;
  enableTilt?: boolean;
  enableMagnetism?: boolean;
  clickEffect?: boolean;
  enableBorderGlow?: boolean;
  particleCount?: number;
  disableAnimations?: boolean;
}) {
  const cardRef = useRef<HTMLDivElement>(null);
  const particlesRef = useRef<HTMLDivElement[]>([]);
  const timeoutsRef = useRef<NodeJS.Timeout[]>([]);
  const isHoveredRef = useRef(false);
  const memoizedParticles = useRef<HTMLDivElement[]>([]);
  const particlesInitialized = useRef(false);
  const magnetismAnimationRef = useRef<gsap.core.Tween | null>(null);
  
  const [isHoveredState, setIsHoveredState] = useState(false);
  const { resolvedTheme } = useTheme();
  
  const currentGlowColor = glowColor !== DEFAULT_GLOW_COLOR 
    ? glowColor 
    : (resolvedTheme === 'light' ? '14, 206, 240' : '0, 213, 255');

  const initializeParticles = useCallback(() => {
    if (particlesInitialized.current || !cardRef.current) return;

    const { width, height } = cardRef.current.getBoundingClientRect();
    memoizedParticles.current = Array.from({ length: particleCount }, () =>
      createParticleElement(Math.random() * width, Math.random() * height, currentGlowColor)
    ) as HTMLDivElement[];
    particlesInitialized.current = true;
  }, [particleCount, currentGlowColor]);

  const clearAllParticles = useCallback(() => {
    timeoutsRef.current.forEach(clearTimeout);
    timeoutsRef.current = [];
    magnetismAnimationRef.current?.kill();

    particlesRef.current.forEach(particle => {
      gsap.to(particle, {
        scale: 0,
        opacity: 0,
        duration: 0.3,
        ease: 'back.in(1.7)',
        onComplete: () => {
          particle.parentNode?.removeChild(particle);
        }
      });
    });
    particlesRef.current = [];
  }, []);

  const animateParticles = useCallback(() => {
    if (!cardRef.current || !isHoveredRef.current) return;

    if (!particlesInitialized.current) {
      initializeParticles();
    }

    memoizedParticles.current.forEach((particle, index) => {
      const timeoutId = setTimeout(() => {
        if (!isHoveredRef.current || !cardRef.current) return;

        const clone = particle.cloneNode(true) as HTMLDivElement;
        cardRef.current.appendChild(clone);
        particlesRef.current.push(clone);

        gsap.fromTo(clone, { scale: 0, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.3, ease: 'back.out(1.7)' });

        gsap.to(clone, {
          x: (Math.random() - 0.5) * 100,
          y: (Math.random() - 0.5) * 100,
          rotation: Math.random() * 360,
          duration: 2 + Math.random() * 2,
          ease: 'none',
          repeat: -1,
          yoyo: true
        });

        gsap.to(clone, {
          opacity: 0.3,
          duration: 1.5,
          ease: 'power2.inOut',
          repeat: -1,
          yoyo: true
        });
      }, index * 100);

      timeoutsRef.current.push(timeoutId);
    });
  }, [initializeParticles]);

  const handleMouseEnter = () => {
    setIsHoveredState(true);
    if (disableAnimations) return;
    isHoveredRef.current = true;
    animateParticles();

    if (enableTilt && cardRef.current) {
      gsap.to(cardRef.current, {
        rotateX: 5,
        rotateY: 5,
        duration: 0.3,
        ease: 'power2.out',
        transformPerspective: 1000
      });
    }
  };

  const handleMouseLeave = () => {
    setIsHoveredState(false);
    if (disableAnimations) return;
    isHoveredRef.current = false;
    clearAllParticles();

    if (enableTilt && cardRef.current) {
      gsap.to(cardRef.current, {
        rotateX: 0,
        rotateY: 0,
        duration: 0.3,
        ease: 'power2.out'
      });
    }

    if (enableMagnetism && cardRef.current) {
      gsap.to(cardRef.current, {
        x: 0,
        y: 0,
        duration: 0.3,
        ease: 'power2.out'
      });
    }

    const borderGlowEl = cardRef.current?.querySelector<HTMLElement>('.border-glow');
    if (borderGlowEl) {
      borderGlowEl.style.opacity = '0';
    }
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (disableAnimations) return;
    if (!cardRef.current) return;

    const element = cardRef.current;
    const rect = element.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;

    if (enableTilt) {
      const rotateX = ((y - centerY) / centerY) * -10;
      const rotateY = ((x - centerX) / centerX) * 10;

      gsap.to(element, {
        rotateX,
        rotateY,
        duration: 0.1,
        ease: 'power2.out',
        transformPerspective: 1000
      });
    }

    if (enableMagnetism) {
      const magnetX = (x - centerX) * 0.05;
      const magnetY = (y - centerY) * 0.05;

      magnetismAnimationRef.current = gsap.to(element, {
        x: magnetX,
        y: magnetY,
        duration: 0.3,
        ease: 'power2.out'
      });
    }

    const borderGlowEl = element.querySelector<HTMLElement>('.border-glow');
    if (borderGlowEl) {
      borderGlowEl.style.background = `radial-gradient(300px circle at ${x}px ${y}px, rgba(${currentGlowColor}, 0.8) 0%, rgba(${currentGlowColor}, 0.4) 30%, transparent 60%)`;
      borderGlowEl.style.opacity = '1';
    }
  };

  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (disableAnimations) return;
    if (!clickEffect || !cardRef.current) return;

    const element = cardRef.current;
    const rect = element.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const maxDistance = Math.max(
      Math.hypot(x, y),
      Math.hypot(x - rect.width, y),
      Math.hypot(x, y - rect.height),
      Math.hypot(x - rect.width, y - rect.height)
    );

    const ripple = document.createElement('div');
    ripple.style.cssText = `
      position: absolute;
      width: ${maxDistance * 2}px;
      height: ${maxDistance * 2}px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(${currentGlowColor}, 0.4) 0%, rgba(${currentGlowColor}, 0.2) 30%, transparent 70%);
      left: ${x - maxDistance}px;
      top: ${y - maxDistance}px;
      pointer-events: none;
      z-index: 1000;
    `;

    element.appendChild(ripple);

    gsap.fromTo(
      ripple,
      {
        scale: 0,
        opacity: 1
      },
      {
        scale: 1,
        opacity: 0,
        duration: 0.8,
        ease: 'power2.out',
        onComplete: () => ripple.remove()
      }
    );
  };

  useEffect(() => {
    return () => {
      isHoveredRef.current = false;
      clearAllParticles();
    };
  }, [clearAllParticles]);

  const cardStyle: React.CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'space-between',
    position: 'relative',
    minHeight: '160px',
    width: '100%',
    padding: '1.25em',
    borderRadius: '20px',
    border: '1px solid #93d5e8ff',
    backgroundColor: '#120F17',
    fontWeight: 300,
    overflow: 'hidden',
    transition: 'transform 0.3s ease, box-shadow 0.3s ease',
    transform: isHoveredState && !disableAnimations ? 'translateY(-2px)' : 'translateY(0)',
    boxShadow: isHoveredState && !disableAnimations 
      ? `0 8px 25px rgba(0, 0, 0, 0.4), 0 0 30px rgba(${currentGlowColor}, 0.2)` 
      : 'none',
    ...style
  };

  return (
    <div
      ref={cardRef}
      className={`${className} magic-bento-card`}
      style={cardStyle}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onMouseMove={handleMouseMove}
      onClick={handleClick}
    >
      {enableBorderGlow && (
        <div
          className="border-glow"
          style={{
            position: 'absolute',
            inset: 0,
            padding: '1px',
            borderRadius: 'inherit',
            pointerEvents: 'none',
            opacity: 0,
            transition: 'opacity 0.3s ease',
            zIndex: 1,
            WebkitMask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)',
            WebkitMaskComposite: 'xor',
            mask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)',
            maskComposite: 'exclude'
          }}
        />
      )}
      {children}
    </div>
  );
}

export default MagicBento;
