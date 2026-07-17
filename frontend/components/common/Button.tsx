'use client';

import React from 'react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ children, className = '', variant = 'primary', size = 'md', ...props }, ref) => {
    const baseStyle = 'inline-flex items-center justify-center font-medium rounded-lg transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed';
    
    const variants = {
      primary: 'bg-slate-950 hover:bg-slate-800 text-white focus:ring-slate-950',
      secondary: 'bg-white hover:bg-slate-50 text-slate-900 border border-slate-200 focus:ring-slate-200 dark:bg-slate-900 dark:border-slate-800 dark:text-slate-100',
      danger: 'bg-red-600 hover:bg-red-700 text-white focus:ring-red-500',
      ghost: 'bg-transparent hover:bg-slate-100 text-slate-600 hover:text-slate-900 focus:ring-slate-200'
    };

    const sizes = {
      sm: 'px-3 py-1.5 text-xs',
      md: 'px-4 py-2 text-sm',
      lg: 'px-5 py-2.5 text-base'
    };

    if (variant === 'ghost') {
      return (
        <button
          ref={ref}
          className={`${baseStyle} ${variants.ghost} ${sizes[size]} ${className}`}
          {...props}
        >
          {children}
        </button>
      );
    }

    return (
      <button
        ref={ref}
        className={`star-border-container relative overflow-hidden inline-flex items-center justify-center font-medium rounded-lg focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed ${className}`}
        style={{
          padding: '5px',
          background: 'rgba(0, 0, 0, 0.1)',
          border: 'none',
          ...props.style
        }}
        {...props}
      >
        <div
          className="border-gradient-bottom"
          style={{
            background: 'radial-gradient(circle, #7e22ce, transparent 35%)',
            animationDuration: '1.5s'
          }}
        />
        <div
          className="border-gradient-top"
          style={{
            background: 'radial-gradient(circle, #7e22ce, transparent 35%)',
            animationDuration: '1.5s'
          }}
        />
        <span 
          className={`relative z-10 flex items-center justify-center gap-1.5 w-full h-full rounded-[3px] ${variants[variant]} ${sizes[size]}`}
          style={{
            transition: 'background-color 200ms ease, color 200ms ease',
          }}
        >
          {children}
        </span>
      </button>
    );
  }
);

Button.displayName = 'Button';
