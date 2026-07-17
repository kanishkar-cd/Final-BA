'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import Link from 'next/link';
import { usePathname, useRouter, useParams } from 'next/navigation';
import { 
  LogOut, 
  Upload, 
  FileText, 
  Database, 
  Tag, 
  Bot, 
  CheckCircle, 
  Layers, 
  ShieldCheck, 
  Home,
  ChevronRight
} from 'lucide-react';
import { useWorkspaceStore } from '@/store/workspaceStore';

// Dock-style magnification sidebar step
function SidebarDockStep({
  step,
  projectId,
  isActive,
  mouseY,
  isExpanded,
}: {
  step: { id: number; label: string; icon: React.ComponentType<any>; path: string };
  projectId: string;
  isActive: boolean;
  mouseY: number;
  isExpanded: boolean;
}) {
  const ref = useRef<HTMLAnchorElement>(null);
  const [scale, setScale] = useState(1);
  const [iconSize, setIconSize] = useState(28);
  const Icon = step.icon;

  useEffect(() => {
    if (!ref.current || mouseY === Infinity) {
      setScale(1);
      setIconSize(isExpanded ? 28 : 32);
      return;
    }
    const rect = ref.current.getBoundingClientRect();
    const center = rect.y + rect.height / 2;
    const dist = Math.abs(mouseY - center);
    const maxDist = 120;
    const minScale = 1;
    const maxScale = isExpanded ? 1.15 : 1.35;
    const minIcon = isExpanded ? 28 : 32;
    const maxIcon = isExpanded ? 36 : 48;

    if (dist > maxDist) {
      setScale(minScale);
      setIconSize(minIcon);
    } else {
      const ratio = 1 - dist / maxDist;
      setScale(minScale + (maxScale - minScale) * ratio);
      setIconSize(minIcon + (maxIcon - minIcon) * ratio);
    }
  }, [mouseY, isExpanded]);

  return (
    <Link
      ref={ref}
      href={`/projects/${projectId}/${step.path}`}
      title={step.label}
      className={`flex items-center group relative ${isExpanded ? 'my-1.5' : 'my-2 justify-center'}`}
      style={{
        transform: `scale(${scale})`,
        transformOrigin: isExpanded ? 'left center' : 'center center',
        transition: 'transform 0.18s cubic-bezier(0.25, 0.46, 0.45, 0.94)',
        height: isExpanded ? `${34 + (scale - 1) * 16}px` : `${36 + (scale - 1) * 24}px`,
        padding: '3px 0',
      }}
    >
      <div
        className={`
          flex items-center justify-center rounded-full shrink-0 shadow-sm transition-colors duration-200
          ${isExpanded ? 'mx-2' : 'mx-auto'}
          ${isActive
            ? 'bg-primary text-primary-foreground shadow-primary/30'
            : 'bg-background text-muted-foreground border border-border group-hover:border-primary/50 group-hover:text-primary group-hover:bg-primary/5'}
        `}
        style={{
          width: `${iconSize}px`,
          height: `${iconSize}px`,
          transition: 'width 0.18s ease, height 0.18s ease, background-color 0.2s ease, border-color 0.2s ease',
        }}
      >
        <Icon style={{ width: `${iconSize * 0.5}px`, height: `${iconSize * 0.5}px`, transition: 'width 0.18s ease, height 0.18s ease' }} />
      </div>

      {isExpanded && (
        <div className="flex flex-col whitespace-nowrap overflow-hidden pr-4">
          <span
            className={`font-medium ${isActive ? 'text-foreground' : 'text-muted-foreground group-hover:text-foreground'}`}
            style={{
              fontSize: `${14 + (scale - 1) * 6}px`,
              transition: 'font-size 0.18s ease, color 0.2s ease',
            }}
          >
            {step.label}
          </span>
        </div>
      )}
    </Link>
  );
}

export const Sidebar: React.FC = () => {
  const pathname = usePathname();
  const router = useRouter();
  const params = useParams();
  const projectId = params?.projectId as string;
  const { workspaces } = useWorkspaceStore();
  const [isExpanded, setIsExpanded] = useState(true);
  const [mouseY, setMouseY] = useState(Infinity);
  const stepsContainerRef = useRef<HTMLDivElement>(null);

  const handleLogout = () => {
    localStorage.removeItem('auth_token');
    router.push('/');
  };

  const currentWorkspace = workspaces.find(w => w.id === projectId);

  // User-facing stages for BA Accelerator
  const steps = [
    { id: 0, label: 'AI Pipeline', icon: Bot, path: 'processing' },
    { id: 1, label: 'Req Analysis', icon: CheckCircle, path: 'requirements' },
    { id: 2, label: 'Outline Review', icon: Layers, path: 'epics' },
    { id: 3, label: 'Story Board', icon: FileText, path: 'stories' },
    { id: 4, label: 'Validation Gate', icon: ShieldCheck, path: 'validation' },
    { id: 5, label: 'Project History', icon: Bot, path: 'history' },
    { id: 6, label: 'Version Control', icon: Database, path: 'versioning' },
    { id: 7, label: 'Final Export', icon: CheckCircle, path: 'export' }
  ];

  useEffect(() => {
    if (!projectId) return;
    const activeStep = steps.find(s => pathname.includes(s.path));
    if (activeStep) {
      localStorage.setItem(`wf_last_visited_${projectId}`, activeStep.path);
    }
  }, [projectId, pathname, steps]);

  const filteredSteps = currentWorkspace?.status === 'completed'
    ? steps.filter(s => s.path === 'export')
    : steps;

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    setMouseY(e.clientY);
  }, []);

  const handleMouseLeave = useCallback(() => {
    setMouseY(Infinity);
  }, []);

  return (
    <div className="flex h-screen select-none shrink-0 z-30 bg-background border-r border-border transition-all duration-500 relative" style={{ width: isExpanded ? '280px' : '68px' }}>
      
      {/* Toggle Button */}
      <button 
        onClick={() => setIsExpanded(!isExpanded)}
        className="absolute -right-3 top-6 w-6 h-6 bg-primary text-primary-foreground rounded-full flex items-center justify-center shadow-md z-40 hover:scale-110 transition-transform"
      >
        <ChevronRight className={`w-4 h-4 transition-transform duration-500 ${!isExpanded ? 'rotate-180' : ''}`} />
      </button>

      <div className={`flex flex-col h-full w-full py-4 overflow-hidden relative`}>
        
        {/* Header */}
        <div className={`${isExpanded ? 'px-5' : 'px-3 justify-center'} flex items-center gap-2 mb-4 shrink-0`}>
          <div className="w-7 h-7 flex items-center justify-center shrink-0">
            <img src="/images_and_videos/logo-think.png" alt="BA Accelerator" className="w-full h-full object-contain" />
          </div>
          {isExpanded && (
            <div className="flex flex-col whitespace-nowrap overflow-hidden transition-opacity duration-300">
              <span className="text-[10px] text-muted-foreground uppercase tracking-widest">{currentWorkspace?.name || 'Workspace'}</span>
            </div>
          )}
        </div>

        {/* Home & Global actions */}
        <div className={`${isExpanded ? 'px-3' : 'px-1'} mb-4 shrink-0 flex flex-col gap-1`}>
          <Link href="/dashboard" className={`flex items-center gap-2 ${isExpanded ? 'px-2' : 'justify-center px-0'} py-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/5 transition-colors group`}>
            <Home className="w-4 h-4 shrink-0 group-hover:scale-110 transition-transform" />
            {isExpanded && <span className="text-[13px] font-medium whitespace-nowrap">Dashboard</span>}
          </Link>
        </div>

        {/* Workflow Steps with Dock Magnification Effect */}
        {projectId && (
          <div className="flex-1 overflow-y-auto overflow-x-hidden px-1 py-2 relative hide-scrollbar">
            {isExpanded && (
              <div className="px-4 mb-3">
                <span className="text-[10px] font-bold tracking-widest text-primary uppercase">Workflow Stages</span>
              </div>
            )}
            
            <div
              ref={stepsContainerRef}
              className={`flex flex-col gap-0 relative w-full ${!isExpanded ? 'items-center' : ''}`}
              onMouseMove={handleMouseMove}
              onMouseLeave={handleMouseLeave}
            >
              {/* Vertical Arc Background Line (expanded only) */}
              {isExpanded && (
                <div className="absolute left-[38px] top-4 bottom-4 w-px bg-gradient-to-b from-transparent via-border to-transparent -z-10" />
              )}
              
              {filteredSteps.map((step) => {
                const isActive = pathname.includes(step.path);
                return (
                  <SidebarDockStep
                    key={step.id}
                    step={step}
                    projectId={projectId}
                    isActive={isActive}
                    mouseY={mouseY}
                    isExpanded={isExpanded}
                  />
                );
              })}
            </div>
          </div>
        )}

        {/* Bottom Actions */}
        <div className={`${isExpanded ? 'px-3' : 'px-1'} mt-auto pt-3 border-t border-border/50 shrink-0 flex flex-col gap-1`}>
          <button
            onClick={handleLogout}
            className={`flex items-center gap-2 ${isExpanded ? 'px-2' : 'justify-center px-0'} py-1.5 rounded-lg text-muted-foreground hover:text-red-500 hover:bg-red-500/10 transition-colors group w-full text-left`}
            title="Logout"
          >
            <LogOut className="w-4 h-4 shrink-0 group-hover:scale-110 transition-transform" />
            {isExpanded && <span className="text-[13px] font-medium whitespace-nowrap">Logout</span>}
          </button>
        </div>
      </div>

      <style dangerouslySetInnerHTML={{__html: `
        .hide-scrollbar::-webkit-scrollbar {
          display: none;
        }
        .hide-scrollbar {
          -ms-overflow-style: none;
          scrollbar-width: none;
        }
      `}} />
    </div>
  );
};
