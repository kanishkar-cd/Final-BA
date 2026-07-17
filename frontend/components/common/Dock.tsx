'use client';

import React, { Children, cloneElement, useEffect, useMemo, useRef, useState, ReactNode } from 'react';
import { motion, useMotionValue, useSpring, useTransform, AnimatePresence, SpringOptions } from 'framer-motion';

export interface DockItemData {
  icon: ReactNode;
  label: string;
  onClick?: () => void;
  className?: string;
}

interface DockItemProps {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
  mouseX: any;
  mouseY: any;
  spring: SpringOptions;
  distance: number;
  magnification: number;
  baseItemSize: number;
  label: string;
  direction: 'horizontal' | 'vertical';
}

function DockItem({
  children,
  className = '',
  onClick,
  mouseX,
  mouseY,
  spring,
  distance,
  magnification,
  baseItemSize,
  label,
  direction
}: DockItemProps) {
  const ref = useRef<HTMLDivElement>(null);
  const isHovered = useMotionValue(0);

  const mouseDistance = useTransform(direction === 'horizontal' ? mouseX : mouseY, (val: number) => {
    if (val === Infinity || val === -Infinity || isNaN(val) || !ref.current) return distance;
    const rect = ref.current.getBoundingClientRect();
    const center = direction === 'horizontal' 
      ? rect.x + rect.width / 2 
      : rect.y + rect.height / 2;
    const diff = val - center;
    if (diff < -distance) return -distance;
    if (diff > distance) return distance;
    return diff;
  });

  const targetSize = useTransform(mouseDistance, [-distance, 0, distance], [baseItemSize, magnification, baseItemSize]);
  const size = useSpring(targetSize, spring);
  const iconScale = useTransform(size, [baseItemSize, magnification], [1, 1.25]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onClick?.();
    }
  };

  const itemStyle: React.CSSProperties = {
    position: 'relative',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: '12px',
    backgroundColor: '#120F17',
    border: '1px solid #2F293A',
    cursor: 'pointer',
    outline: 'none',
    width: '100%',
    height: '100%',
    boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -1px rgba(0, 0, 0, 0.2)'
  };

  return (
    <motion.div
      ref={ref}
      style={{
        width: size,
        height: size,
        ...itemStyle
      }}
      onHoverStart={() => isHovered.set(1)}
      onHoverEnd={() => isHovered.set(0)}
      onFocus={() => isHovered.set(1)}
      onBlur={() => isHovered.set(0)}
      onClick={onClick}
      className={`dock-item ${className}`}
      tabIndex={0}
      role="button"
      aria-haspopup="true"
      aria-label={label}
      onKeyDown={handleKeyDown}
    >
      <motion.div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%', height: '100%', scale: iconScale }}>
        {Children.map(children, child => {
          if (React.isValidElement(child)) {
            return cloneElement(child as React.ReactElement<any>, { isHovered, direction });
          }
          return child;
        })}
      </motion.div>
    </motion.div>
  );
}

interface DockLabelProps {
  children: ReactNode;
  className?: string;
  isHovered?: any;
  direction?: 'horizontal' | 'vertical';
}

function DockLabel({ children, className = '', isHovered, direction = 'horizontal' }: DockLabelProps) {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    if (!isHovered) return;
    const unsubscribe = isHovered.on('change', (latest: number) => {
      setIsVisible(latest === 1);
    });
    return () => unsubscribe();
  }, [isHovered]);

  const labelStyle: React.CSSProperties = direction === 'horizontal' ? {
    position: 'absolute',
    top: '-1.8rem',
    left: '50%',
    width: 'fit-content',
    whiteSpace: 'nowrap',
    borderRadius: '0.375rem',
    border: '1px solid #2F293A',
    backgroundColor: '#120F17',
    padding: '0.2rem 0.5rem',
    fontSize: '0.75rem',
    color: '#fff',
    zIndex: 999
  } : {
    position: 'absolute',
    left: '100%',
    top: '50%',
    marginLeft: '0.75rem',
    width: 'fit-content',
    whiteSpace: 'nowrap',
    borderRadius: '0.375rem',
    border: '1px solid #2F293A',
    backgroundColor: '#120F17',
    padding: '0.2rem 0.5rem',
    fontSize: '0.75rem',
    color: '#fff',
    zIndex: 999
  };

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          initial={{ 
            opacity: 0, 
            scale: 0.9,
            x: direction === 'horizontal' ? '-50%' : '0%',
            y: direction === 'horizontal' ? '0%' : '-50%'
          }}
          animate={{ 
            opacity: 1, 
            scale: 1,
            x: direction === 'horizontal' ? '-50%' : '0%',
            y: direction === 'horizontal' ? '0%' : '-50%'
          }}
          exit={{ 
            opacity: 0, 
            scale: 0.9,
            x: direction === 'horizontal' ? '-50%' : '0%',
            y: direction === 'horizontal' ? '0%' : '-50%'
          }}
          transition={{ duration: 0.15 }}
          style={labelStyle}
          className={`dock-label ${className}`}
          role="tooltip"
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function DockIcon({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div 
      className={`dock-icon ${className}`}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: '100%',
        height: '100%',
        color: '#0ECEF0'
      }}
    >
      {children}
    </div>
  );
}

interface DockProps {
  items: DockItemData[];
  className?: string;
  spring?: SpringOptions;
  magnification?: number;
  distance?: number;
  panelHeight?: number;
  dockHeight?: number;
  baseItemSize?: number;
  direction?: 'horizontal' | 'vertical';
}

export function Dock({
  items,
  className = '',
  spring = { mass: 0.1, stiffness: 150, damping: 12 },
  magnification = 60,
  distance = 150,
  panelHeight = 54,
  dockHeight = 200,
  baseItemSize = 40,
  direction = 'horizontal'
}: DockProps) {
  const mouseX = useMotionValue(Infinity);
  const mouseY = useMotionValue(Infinity);
  const isHovered = useMotionValue(0);

  const maxHeight = useMemo(
    () => Math.max(dockHeight, magnification + magnification / 2 + 4),
    [magnification, dockHeight]
  );
  
  const heightRow = useTransform(isHovered, [0, 1], [panelHeight, maxHeight]);
  const animatedSize = useSpring(heightRow, spring);

  const containerStyle: React.CSSProperties = direction === 'horizontal' ? {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '100%',
    height: animatedSize as any
  } : {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    width: animatedSize as any
  };

  const panelStyle: React.CSSProperties = direction === 'horizontal' ? {
    display: 'flex',
    alignItems: 'flex-end',
    width: 'fit-content',
    gap: '0.75rem',
    borderRadius: '1.25rem',
    backgroundColor: '#0c0b0f',
    border: '1px solid #2F293A',
    padding: '0.375rem 0.5rem',
    height: `${panelHeight}px`
  } : {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    height: 'fit-content',
    gap: '0.75rem',
    borderRadius: '1.25rem',
    backgroundColor: '#0c0b0f',
    border: '1px solid #2F293A',
    padding: '0.5rem 0.375rem',
    width: `${panelHeight}px`
  };

  return (
    <motion.div 
      style={containerStyle} 
      className={`dock-outer ${className}`}
    >
      <motion.div
        onMouseMove={(e) => {
          isHovered.set(1);
          mouseX.set(e.clientX);
          mouseY.set(e.clientY);
        }}
        onMouseLeave={() => {
          isHovered.set(0);
          mouseX.set(Infinity);
          mouseY.set(Infinity);
        }}
        style={panelStyle}
        className="dock-panel"
        role="toolbar"
        aria-label="Application dock"
      >
        {items.map((item, index) => (
          <DockItem
            key={index}
            onClick={item.onClick}
            className={item.className}
            mouseX={mouseX}
            mouseY={mouseY}
            spring={spring}
            distance={distance}
            magnification={magnification}
            baseItemSize={baseItemSize}
            label={item.label}
            direction={direction}
          >
            <DockIcon>{item.icon}</DockIcon>
            <DockLabel>{item.label}</DockLabel>
          </DockItem>
        ))}
      </motion.div>
    </motion.div>
  );
}

export default Dock;
