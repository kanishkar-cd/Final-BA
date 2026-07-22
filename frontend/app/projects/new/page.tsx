'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/common/Button';
import { useWorkspaceStore } from '@/store/workspaceStore';
import { 
  ArrowLeft, ArrowRight, CheckCircle2, Upload, FileText, Check, AlertTriangle
} from 'lucide-react';
import { FaJira, FaConfluence, FaGoogleDrive, FaFileWord, FaMicrosoft } from 'react-icons/fa';
import { cn } from '@/lib/utils';
import { ThinkingIndicator, MOCK_PIPELINE_STAGES } from '@/components/common/ThinkingIndicator';
import { api } from '@/services/api';

export default function NewProjectPage() {
  const router = useRouter();
  const { createWorkspace } = useWorkspaceStore();
  
  const [newName, setNewName] = useState('');
  const [activeSource, setActiveSource] = useState<string>('upload');
  const [validationMode, setValidationMode] = useState<'final' | 'every-step'>('every-step');
  const [connections, setConnections] = useState<Record<string, boolean>>({});
  const [isVerifying, setIsVerifying] = useState<Record<string, boolean>>({});
  const [verifyErrors, setVerifyErrors] = useState<Record<string, string | null>>({});
  const [isProcessing, setIsProcessing] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Step 7 parameters
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.8);
  const [maxRetryAttempts, setMaxRetryAttempts] = useState(3);

  // File upload state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  // Jira fields
  const [jiraIssueKey, setJiraIssueKey] = useState('PROJ-25');
  const [jiraIncludeComments, setJiraIncludeComments] = useState(false);



  // Google Drive fields
  const [gdriveLink, setGdriveLink] = useState('');

  // SharePoint fields
  const [sharepointUrl, setSharepointUrl] = useState('https://itclouddestinations.sharepoint.com');
  const [sharepointLibrary, setSharepointLibrary] = useState('BA Accelerator');
  const [sharepointFolderPath, setSharepointFolderPath] = useState('');
  const [sharepointFileName, setSharepointFileName] = useState('');
  const [sharepointTenantId, setSharepointTenantId] = useState('');
  const [sharepointClientId, setSharepointClientId] = useState('');
  const [sharepointClientSecret, setSharepointClientSecret] = useState('');
  const [sharepointFiles, setSharepointFiles] = useState<any[]>([]);
  const [selectedSharepointFileName, setSelectedSharepointFileName] = useState<string>('all');

  // Azure DevOps fields
  const [adoOrg, setAdoOrg] = useState('');
  const [adoProject, setAdoProject] = useState('');
  const [adoPat, setAdoPat] = useState('');
  const [adoImportMethod, setAdoImportMethod] = useState<'work-item'>('work-item');
  const [adoWorkItemId, setAdoWorkItemId] = useState('');

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      markConnected(activeSource);
    }
  };

  const handleVerifySharepoint = async () => {
    if (!sharepointUrl.trim() || !sharepointLibrary.trim()) return;
    setIsVerifying(prev => ({ ...prev, sharepoint: true }));
    setVerifyErrors(prev => ({ ...prev, sharepoint: null }));
    try {
      const res = await api.connectSharePoint(
        sharepointUrl, sharepointLibrary, sharepointFolderPath, sharepointFileName,
        sharepointTenantId, sharepointClientId, sharepointClientSecret
      );
      const files = res.supported_files || [];
      setSharepointFiles(files);
      if (files.length === 1) {
        setSelectedSharepointFileName(files[0].name);
      } else {
        setSelectedSharepointFileName('all');
      }
      markConnected('sharepoint');
    } catch (err: any) {
      setVerifyErrors(prev => ({ ...prev, sharepoint: err.message || 'SharePoint verification failed. Please check Site URL and Document Library.' }));
      setConnections(prev => ({ ...prev, sharepoint: false }));
    } finally {
      setIsVerifying(prev => ({ ...prev, sharepoint: false }));
    }
  };

  const handleVerifyJira = async () => {
    if (!jiraIssueKey.trim()) return;
    setIsVerifying(prev => ({ ...prev, jira: true }));
    setVerifyErrors(prev => ({ ...prev, jira: null }));
    try {
      await api.fetchJira(jiraIssueKey, jiraIncludeComments);
      markConnected('jira');
    } catch (err: any) {
      setVerifyErrors(prev => ({ ...prev, jira: err.message || 'Verification failed. Please check your Jira configuration and issue key.' }));
      setConnections(prev => ({ ...prev, jira: false }));
    } finally {
      setIsVerifying(prev => ({ ...prev, jira: false }));
    }
  };



  const handleVerifyAdo = async () => {
    if (!adoOrg.trim() || !adoProject.trim() || !adoPat.trim() || !adoWorkItemId.trim()) return;
    setIsVerifying(prev => ({ ...prev, ado: true }));
    setVerifyErrors(prev => ({ ...prev, ado: null }));
    try {
      await api.fetchAdoWorkItem(adoOrg, adoProject, adoPat, adoWorkItemId);
      markConnected('ado');
    } catch (err: any) {
      setVerifyErrors(prev => ({ ...prev, ado: err.message || 'Verification failed. Please check your Azure DevOps configuration.' }));
      setConnections(prev => ({ ...prev, ado: false }));
    } finally {
      setIsVerifying(prev => ({ ...prev, ado: false }));
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    
    const newId = newName.toLowerCase().replace(/\s+/g, '-');
    setIsProcessing(true);
    setCreateError(null);

    try {
      if (activeSource === 'upload' && selectedFile) {
        // Upload file first, then store file_path and let processing page start the workflow
        const importRes = await api.importDocument(selectedFile);
        localStorage.setItem(`wf_file_path_${newId}`, importRes.file_path);
        localStorage.setItem(`workflow_started_${newId}`, 'false');
      } else if (activeSource === 'sharepoint') {
        const targetFile = (selectedSharepointFileName && selectedSharepointFileName !== 'all') ? selectedSharepointFileName : sharepointFileName;
        const res = await api.startWorkflowFromSharePoint(
          sharepointUrl, sharepointLibrary, sharepointFolderPath, targetFile,
          confidenceThreshold, maxRetryAttempts, newId, validationMode,
          sharepointTenantId, sharepointClientId, sharepointClientSecret
        );
        localStorage.setItem(`workflow_started_${newId}`, 'true');
        localStorage.setItem(`wf_id_${newId}`, res.workflow_id || newId);
        localStorage.setItem(`sharepoint_url_${newId}`, sharepointUrl);
        localStorage.setItem(`sharepoint_path_${newId}`, `${sharepointLibrary}/${sharepointFolderPath}/${targetFile}`);
      } else if (activeSource === 'ado') {
        const res = await api.startWorkflowFromAdo(adoOrg, adoProject, adoPat, adoWorkItemId, confidenceThreshold, maxRetryAttempts, newId, validationMode);
        localStorage.setItem(`workflow_started_${newId}`, 'true');
        localStorage.setItem(`wf_id_${newId}`, res.workflow_id || newId);
        localStorage.setItem(`ado_org_${newId}`, adoOrg);
        localStorage.setItem(`ado_project_${newId}`, adoProject);
        localStorage.setItem(`ado_pat_${newId}`, adoPat);
      } else if (activeSource === 'jira') {
        const res = await api.startWorkflowFromJira(jiraIssueKey, jiraIncludeComments, confidenceThreshold, maxRetryAttempts, newId, validationMode);
        localStorage.setItem(`workflow_started_${newId}`, 'true');
        localStorage.setItem(`wf_id_${newId}`, res.workflow_id || newId);
      } else if (activeSource === 'confluence') {
        const res = await api.startWorkflowFromConfluence(confluencePageId, confidenceThreshold, maxRetryAttempts, newId, validationMode);
        localStorage.setItem(`workflow_started_${newId}`, 'true');
        localStorage.setItem(`wf_id_${newId}`, res.workflow_id || newId);
      } else {
        // No real source selected — go through processing with mock
        localStorage.setItem(`workflow_started_${newId}`, 'true');
        localStorage.setItem(`wf_id_${newId}`, newId);
      }
      localStorage.setItem(`wf_validation_mode_${newId}`, validationMode);
      createWorkspace(newName, `Generated from ${activeSource}`);
      router.push(`/projects/${newId}/processing`);
    } catch (err: any) {
      console.error("Failed to start workflow:", err);
      const msg: string = err?.message || String(err);
      if (msg.toLowerCase().includes('failed to fetch') || msg.toLowerCase().includes('networkerror')) {
        setCreateError('Cannot reach the backend. Make sure the FastAPI server is running on port 8000.');
      } else {
        setCreateError(`Failed to start workflow: ${msg}`);
      }
      setIsProcessing(false);
    }
  };

  const handleProcessingComplete = () => {
    const newId = newName.toLowerCase().replace(/\s+/g, '-');
    createWorkspace(newName, 'Generated from PRD'); 
    router.push(`/projects/${newId}/requirements`);
  };

  const markConnected = (srcId: string) => {
    setConnections(prev => ({ ...prev, [srcId]: true }));
  };

  const sources = [
    { 
      id: 'upload', 
      label: 'Local Upload', 
      desc: 'Upload PDF, DOC, DOCX, XLS and XLSX files directly.',
      icon: <FaFileWord className="w-5 h-5 text-blue-600" />,
      enabled: true
    },
    { 
      id: 'jira', 
      label: 'Jira Cloud', 
      desc: 'Import requirements directly from Jira Epics or Stories.',
      icon: <FaJira className="w-5 h-5 text-blue-500" />,
      enabled: true
    },
    { 
      id: 'gdrive', 
      label: 'Google Drive', 
      desc: 'Import documents using a Google Drive shared link.',
      icon: <FaGoogleDrive className="w-5 h-5 text-green-500" />,
      enabled: true
    },
    { 
      id: 'sharepoint', 
      label: 'SharePoint', 
      desc: 'Connect to Microsoft SharePoint document libraries.',
      icon: <FaMicrosoft className="w-5 h-5 text-teal-600" />,
      enabled: true
    },
    {
      id: 'voice',
      label: 'Voice Transcript',
      desc: 'Connect to Voice and speech-to-text transcripts.',
      icon: <FileText className="w-5 h-5 text-purple-600" />,
      enabled: true
    },
    {
      id: 'ado',
      label: 'Azure DevOps',
      desc: 'Connect to Azure DevOps Boards and Wikis.',
      icon: <FileText className="w-5 h-5 text-blue-600" />,
      enabled: true
    }
  ];

  return (
    <div className="flex-1 flex flex-col h-full bg-background overflow-hidden relative">
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-5xl mx-auto p-6 md:p-8 lg:p-12">
          
          <Link href="/dashboard" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-primary transition-colors mb-8 group">
            <ArrowLeft className="w-4 h-4 group-hover:-translate-x-1 transition-transform" />
            Back to Dashboard
          </Link>
          
          <div className="mb-8">
            <h1 className="text-3xl font-bold tracking-tight text-foreground mb-2">Create New Project</h1>
            <p className="text-muted-foreground text-sm max-w-2xl">
              Initialize a new requirements parsing workflow. Provide your PRD documents or connect to your existing systems to extract structured requirements.
            </p>
          </div>

          <form onSubmit={handleCreate} className="space-y-12">
            
            {/* Step 1: Name */}
            <section className="space-y-4">
              <div className="flex items-center gap-3">
                <div className="w-6 h-6 rounded-full bg-primary/10 text-primary flex items-center justify-center text-xs font-bold">1</div>
                <h2 className="text-lg font-bold">Project Details</h2>
              </div>
              <div className="pl-9 max-w-2xl">
                <label className="text-sm font-semibold text-foreground mb-1.5 block">Project Name <span className="text-red-500">*</span></label>
                <input 
                  type="text" 
                  placeholder="e.g. E-Commerce Checkout Redesign"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="w-full bg-background border border-input rounded-xl px-4 py-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary shadow-sm"
                  required
                />
              </div>
            </section>

            {/* Step 2: Input Method */}
            <section className="space-y-4">
              <div className="flex items-center gap-3">
                <div className="w-6 h-6 rounded-full bg-primary/10 text-primary flex items-center justify-center text-xs font-bold">2</div>
                <h2 className="text-lg font-bold">Document Source</h2>
              </div>
              <div className="pl-9 space-y-6">
                
                {/* Horizontal Scrollable Sources */}
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
                  {sources.map(src => {
                    const isConnected = connections[src.id];
                    const isActive = activeSource === src.id;
                    
                    return (
                      <button
                        key={src.id}
                        type="button"
                        onClick={() => src.enabled && setActiveSource(src.id as any)}
                        disabled={!src.enabled}
                        className={cn(
                          "flex flex-col text-left p-5 rounded-xl border transition-all relative overflow-hidden group",
                          !src.enabled ? "opacity-60 border-dashed bg-muted/20 cursor-not-allowed" :
                          isActive ? "border-primary bg-primary/5 ring-1 ring-primary shadow-md" : "border-border bg-card hover:border-border/80 hover:bg-accent/30 shadow-sm"
                        )}
                      >
                        <div className="flex justify-between items-start w-full mb-4">
                          <div className="w-10 h-10 rounded-xl bg-background border border-border shadow-sm flex items-center justify-center">
                            {src.icon}
                          </div>
                          {isActive && src.enabled && <CheckCircle2 className="w-5 h-5 text-primary" />}
                          {!src.enabled && (
                            <span className="text-[8px] font-bold text-muted-foreground bg-muted border border-border px-1.5 py-0.5 rounded uppercase tracking-wider">Soon</span>
                          )}
                        </div>
                        <div>
                          <div className="font-bold text-sm text-foreground mb-1">{src.label}</div>
                          <div className="text-xs text-muted-foreground leading-relaxed line-clamp-2">{src.desc}</div>
                        </div>
                        {isConnected && src.enabled && (
                          <div className="mt-3 text-[10px] font-bold text-green-600 bg-green-500/10 px-2 py-1 rounded w-fit uppercase tracking-wider">Connected</div>
                        )}
                      </button>
                    );
                  })}
                </div>

                {/* Dynamic Connection Form Panel */}
                <div className="bg-card border border-border rounded-xl p-8 shadow-sm">
                  
                  {activeSource === 'upload' && (
                    <div className="max-w-2xl">
                      <h3 className="text-lg font-bold mb-1">Local Upload</h3>
                      <p className="text-sm text-muted-foreground mb-6">Upload PDF, DOC, DOCX, XLS, XLSX or Voice recordings.</p>
                      <div className="space-y-5">
                        <input 
                          type="file" 
                          ref={fileInputRef} 
                          onChange={handleFileChange} 
                          className="hidden" 
                          accept=".pdf,.docx,.txt"
                        />
                        <div 
                          onClick={() => fileInputRef.current?.click()}
                          className="p-8 border-2 border-dashed border-border rounded-xl bg-muted/10 text-center hover:bg-muted/30 transition-colors cursor-pointer flex flex-col items-center justify-center gap-4"
                        >
                          <div className="w-16 h-16 rounded-full bg-background border border-border flex items-center justify-center text-muted-foreground shadow-sm">
                            <Upload className="w-6 h-6" />
                          </div>
                          <div>
                            <div className="text-sm font-semibold text-foreground mb-1">
                              {selectedFile ? `Selected: ${selectedFile.name}` : "Drag and drop your files here"}
                            </div>
                            <div className="text-xs text-muted-foreground">
                              {selectedFile ? `${Math.round(selectedFile.size / 1024)} KB` : "or click to browse from your computer"}
                            </div>
                          </div>
                          <Button type="button" size="sm" className="mt-2 bg-secondary text-secondary-foreground">
                            {selectedFile ? "Change File" : "Select File"}
                          </Button>
                        </div>
                      </div>
                    </div>
                  )}

                  {activeSource === 'jira' && (
                    <div className="max-w-2xl">
                      <h3 className="text-lg font-bold mb-1">Connect Jira Cloud</h3>
                      <p className="text-sm text-muted-foreground mb-6">Import issue lists and backlog epics into parsing steps.</p>
                      
                      <div className="space-y-5">
                        <div className="space-y-1.5">
                          <label className="text-xs font-semibold text-foreground">Jira Issue Key</label>
                          <input 
                            type="text" 
                            value={jiraIssueKey}
                            onChange={(e) => setJiraIssueKey(e.target.value)}
                            placeholder="e.g. SHOP-101" 
                            className="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm" 
                            required
                          />
                        </div>
                        <div className="flex items-center gap-2">
                          <input 
                            type="checkbox" 
                            id="jiraComments"
                            checked={jiraIncludeComments}
                            onChange={(e) => setJiraIncludeComments(e.target.checked)}
                            className="rounded border-input text-primary focus:ring-primary" 
                          />
                          <label htmlFor="jiraComments" className="text-xs font-semibold text-foreground select-none cursor-pointer">Include comments</label>
                        </div>
                        <div className="flex gap-3 pt-2 items-center">
                          <Button 
                            type="button" 
                            size="sm" 
                            className="bg-primary hover:bg-primary/90 text-primary-foreground" 
                            onClick={handleVerifyJira}
                            disabled={isVerifying['jira']}
                          >
                            {isVerifying['jira'] ? 'Verifying...' : 'Verify Connection'}
                          </Button>
                        </div>
                        {verifyErrors['jira'] && (
                          <div className="text-xs text-red-500 font-medium">
                            {verifyErrors['jira']}
                          </div>
                        )}
                      </div>
                    </div>
                  )}



                  {activeSource === 'gdrive' && (
                    <div className="max-w-2xl">
                      <h3 className="text-lg font-bold mb-1">Connect Google Drive</h3>
                      <p className="text-sm text-muted-foreground mb-6">Provide a shared link to your PRD documents or folders.</p>
                      
                      <div className="space-y-5">
                        <div className="space-y-1.5">
                          <label className="text-xs font-semibold text-foreground">Google Drive Shared Link</label>
                          <input type="url" value={gdriveLink} onChange={(e) => setGdriveLink(e.target.value)} placeholder="https://drive.google.com/file/d/..." className="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm" />
                        </div>
                        <div className="flex gap-3 pt-2">
                          <Button type="button" size="sm" className="bg-primary hover:bg-primary/90 text-primary-foreground" onClick={() => markConnected('gdrive')}>Connect Drive</Button>
                        </div>
                      </div>
                    </div>
                  )}

                  {activeSource === 'sharepoint' && (
                    <div className="max-w-2xl">
                      <h3 className="text-lg font-bold mb-1">Connect SharePoint</h3>
                      <p className="text-sm text-muted-foreground mb-6">Authenticate via Microsoft Graph API / Entra ID and verify site and folder existence.</p>
                      
                      <div className="space-y-5">
                        <div className="space-y-1.5">
                          <label className="text-xs font-semibold text-foreground">SharePoint Site URL <span className="text-red-500">*</span></label>
                          <input 
                            type="url" 
                            value={sharepointUrl} 
                            onChange={(e) => setSharepointUrl(e.target.value)} 
                            placeholder="https://itclouddestinations.sharepoint.com" 
                            className="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm" 
                            required
                          />
                        </div>

                        <div className="space-y-1.5">
                          <label className="text-xs font-semibold text-foreground">Document Library <span className="text-red-500">*</span></label>
                          <input 
                            type="text" 
                            value={sharepointLibrary} 
                            onChange={(e) => setSharepointLibrary(e.target.value)} 
                            placeholder="e.g. BA Accelerator or Shared Documents" 
                            className="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm" 
                            required
                          />
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                          <div className="space-y-1.5">
                            <label className="text-xs font-semibold text-foreground">Folder Path <span className="text-muted-foreground font-normal">(Optional)</span></label>
                            <input 
                              type="text" 
                              value={sharepointFolderPath} 
                              onChange={(e) => setSharepointFolderPath(e.target.value)} 
                              placeholder="e.g. Requirements or PRD" 
                              className="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm" 
                            />
                          </div>

                          <div className="space-y-1.5">
                            <label className="text-xs font-semibold text-foreground">File Name <span className="text-muted-foreground font-normal">(Optional)</span></label>
                            <input 
                              type="text" 
                              value={sharepointFileName} 
                              onChange={(e) => setSharepointFileName(e.target.value)} 
                              placeholder="e.g. Sample_PRD_Document.pdf" 
                              className="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm" 
                            />
                          </div>
                        </div>

                        {/* Optional Entra ID Authentication Details */}
                        <details className="border border-border/80 rounded-lg p-3 bg-muted/10 text-xs">
                          <summary className="font-semibold text-foreground cursor-pointer select-none">
                            Microsoft Entra ID App Credentials (Optional for Live OAuth Graph API)
                          </summary>
                          <div className="mt-3 space-y-3">
                            <div>
                              <label className="text-[11px] font-semibold text-muted-foreground block mb-1">Tenant ID</label>
                              <input 
                                type="text" 
                                value={sharepointTenantId} 
                                onChange={(e) => setSharepointTenantId(e.target.value)} 
                                placeholder="e.g. 00000000-0000-0000-0000-000000000000" 
                                className="w-full bg-background border border-input rounded px-2.5 py-1.5 text-xs font-mono" 
                              />
                            </div>
                            <div>
                              <label className="text-[11px] font-semibold text-muted-foreground block mb-1">Client ID (App Registration)</label>
                              <input 
                                type="text" 
                                value={sharepointClientId} 
                                onChange={(e) => setSharepointClientId(e.target.value)} 
                                placeholder="e.g. 11111111-1111-1111-1111-111111111111" 
                                className="w-full bg-background border border-input rounded px-2.5 py-1.5 text-xs font-mono" 
                              />
                            </div>
                            <div>
                              <label className="text-[11px] font-semibold text-muted-foreground block mb-1">Client Secret</label>
                              <input 
                                type="password" 
                                value={sharepointClientSecret} 
                                onChange={(e) => setSharepointClientSecret(e.target.value)} 
                                placeholder="••••••••••••••••••••••••" 
                                className="w-full bg-background border border-input rounded px-2.5 py-1.5 text-xs font-mono" 
                              />
                            </div>
                          </div>
                        </details>
                        <div className="flex gap-3 pt-2 items-center">
                          <Button 
                            type="button" 
                            size="sm" 
                            className="bg-primary hover:bg-primary/90 text-primary-foreground font-semibold px-4 py-2 rounded-lg" 
                            onClick={handleVerifySharepoint}
                            disabled={isVerifying['sharepoint']}
                          >
                            {isVerifying['sharepoint'] ? 'Connecting...' : 'Connect SharePoint'}
                          </Button>
                          {connections['sharepoint'] && (
                            <span className="text-xs font-bold text-green-600 bg-green-500/10 border border-green-500/20 px-3 py-1.5 rounded-lg flex items-center gap-1.5">
                              <CheckCircle2 className="w-4 h-4 text-green-600" />
                              Connected Successfully
                            </span>
                          )}
                        </div>

                        {verifyErrors['sharepoint'] && (
                          <div className="text-xs text-red-500 font-medium bg-red-500/10 p-3 rounded-lg border border-red-500/20">
                            {verifyErrors['sharepoint']}
                          </div>
                        )}

                        {connections['sharepoint'] && sharepointFiles.length > 0 && (
                          <div className="mt-4 p-4 bg-muted/20 border border-border rounded-xl space-y-3">
                            <div className="text-xs font-bold text-foreground flex items-center justify-between">
                              <span>Found {sharepointFiles.length} Supported Document{sharepointFiles.length > 1 ? 's' : ''}</span>
                              <span className="text-[10px] text-muted-foreground">Select file to extract</span>
                            </div>
                            
                            <div className="space-y-1.5 text-xs">
                              {sharepointFiles.length > 1 && (
                                <label 
                                  className={cn(
                                    "flex items-center justify-between p-2.5 rounded-lg border cursor-pointer transition-all",
                                    selectedSharepointFileName === 'all' ? "border-primary bg-primary/5 ring-1 ring-primary" : "border-border/60 hover:bg-accent/40"
                                  )}
                                >
                                  <div className="flex items-center gap-2.5">
                                    <input 
                                      type="radio" 
                                      name="sp_file_select" 
                                      checked={selectedSharepointFileName === 'all'} 
                                      onChange={() => setSelectedSharepointFileName('all')} 
                                      className="text-primary focus:ring-primary"
                                    />
                                    <span className="font-semibold text-foreground">Extract All Documents ({sharepointFiles.length} Files)</span>
                                  </div>
                                  <span className="text-[10px] uppercase font-mono bg-primary/10 text-primary px-1.5 py-0.5 rounded font-bold">ALL</span>
                                </label>
                              )}

                              {sharepointFiles.map((file: any, idx: number) => (
                                <label 
                                  key={idx} 
                                  className={cn(
                                    "flex items-center justify-between p-2.5 rounded-lg border cursor-pointer transition-all",
                                    selectedSharepointFileName === file.name ? "border-primary bg-primary/5 ring-1 ring-primary" : "border-border/60 hover:bg-accent/40"
                                  )}
                                >
                                  <div className="flex items-center gap-2.5">
                                    <input 
                                      type="radio" 
                                      name="sp_file_select" 
                                      checked={selectedSharepointFileName === file.name} 
                                      onChange={() => setSelectedSharepointFileName(file.name)} 
                                      className="text-primary focus:ring-primary"
                                    />
                                    <span className="font-medium text-foreground">{file.name}</span>
                                  </div>
                                  <span className="text-[10px] uppercase font-mono bg-accent px-1.5 py-0.5 rounded font-bold">{file.extension}</span>
                                </label>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {activeSource === 'voice' && (
                    <div className="max-w-2xl">
                      <h3 className="text-lg font-bold mb-1">Voice Transcript</h3>
                      <p className="text-sm text-muted-foreground mb-6">Upload audio recordings or speech-to-text transcripts.</p>
                      <div className="space-y-5">
                        <input 
                          type="file" 
                          ref={fileInputRef} 
                          onChange={handleFileChange} 
                          className="hidden" 
                          accept="audio/*,.txt,.pdf,.docx"
                        />
                        <div 
                          onClick={() => fileInputRef.current?.click()}
                          className="p-8 border-2 border-dashed border-border rounded-xl bg-muted/10 text-center hover:bg-muted/30 transition-colors cursor-pointer flex flex-col items-center justify-center gap-4"
                        >
                          <div className="w-16 h-16 rounded-full bg-background border border-border flex items-center justify-center text-muted-foreground shadow-sm">
                            <Upload className="w-6 h-6" />
                          </div>
                          <div>
                            <div className="text-sm font-semibold text-foreground mb-1">
                              {selectedFile ? `Selected: ${selectedFile.name}` : "Drag and drop your audio files here"}
                            </div>
                            <div className="text-xs text-muted-foreground">
                              {selectedFile ? `${Math.round(selectedFile.size / 1024)} KB` : "or click to browse from your computer"}
                            </div>
                          </div>
                          <Button type="button" size="sm" className="mt-2 bg-secondary text-secondary-foreground">
                            {selectedFile ? "Change File" : "Select File"}
                          </Button>
                        </div>
                      </div>
                    </div>
                  )}

                  {activeSource === 'ado' && (
                    <div className="max-w-2xl">
                      <h3 className="text-lg font-bold mb-1">Import From Azure DevOps</h3>
                      <p className="text-sm text-muted-foreground mb-6">Connect to Azure DevOps Boards and Wikis.</p>
                      
                      <div className="space-y-5">
                        <div className="border-b border-border pb-2 mb-4">
                          <h4 className="text-sm font-bold text-foreground">Connection</h4>
                        </div>
                        <div className="space-y-1.5">
                          <label className="text-xs font-semibold text-foreground">Organization</label>
                          <input type="text" value={adoOrg} onChange={(e) => setAdoOrg(e.target.value)} placeholder="e.g. my-org" className="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm" />
                        </div>
                        <div className="space-y-1.5">
                          <label className="text-xs font-semibold text-foreground">Project</label>
                          <input type="text" value={adoProject} onChange={(e) => setAdoProject(e.target.value)} placeholder="e.g. MyProject" className="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm" />
                        </div>
                        <div className="space-y-1.5">
                          <label className="text-xs font-semibold text-foreground">PAT</label>
                          <input type="password" value={adoPat} onChange={(e) => setAdoPat(e.target.value)} placeholder="Personal Access Token" className="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm" />
                        </div>

                        <div className="border-b border-border pb-2 mb-4 mt-6">
                          <h4 className="text-sm font-bold text-foreground">Import Method</h4>
                        </div>
                        
                        <div className="space-y-3 mb-4">
                          <label className="flex items-center gap-2 cursor-pointer opacity-50">
                            <input type="radio" name="adoImportMethod" value="saved-query" disabled className="text-primary focus:ring-primary cursor-not-allowed" />
                            <span className="text-sm font-medium">Saved Query (Coming soon)</span>
                          </label>
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input type="radio" name="adoImportMethod" value="work-item" checked={adoImportMethod === 'work-item'} onChange={() => setAdoImportMethod('work-item')} className="text-primary focus:ring-primary" />
                            <span className="text-sm font-medium">Work Item ID</span>
                          </label>
                        </div>

                        {adoImportMethod === 'work-item' && (
                          <div className="space-y-1.5">
                            <label className="text-xs font-semibold text-foreground">Work Item ID</label>
                            <input type="text" value={adoWorkItemId} onChange={(e) => setAdoWorkItemId(e.target.value)} placeholder="e.g. 12345" className="w-full bg-background border border-input rounded-lg px-3 py-2 text-sm" />
                          </div>
                        )}
                        
                        <div className="flex gap-3 pt-2 items-center">
                          <Button 
                            type="button" 
                            size="sm" 
                            className="bg-primary hover:bg-primary/90 text-primary-foreground" 
                            onClick={handleVerifyAdo}
                            disabled={isVerifying['ado']}
                          >
                            {isVerifying['ado'] ? 'Verifying...' : 'Verify Connection'}
                          </Button>
                        </div>
                        {verifyErrors['ado'] && (
                          <div className="text-xs text-red-500 font-medium">
                            {verifyErrors['ado']}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </section>

            {/* Step 3: Preferences & Quality Gates */}
            <section className="space-y-4">
              <div className="flex items-center gap-3">
                <div className="w-6 h-6 rounded-full bg-primary/10 text-primary flex items-center justify-center text-xs font-bold">3</div>
                <h2 className="text-lg font-bold">Quality & Validation Setup</h2>
              </div>
              <div className="pl-9 max-w-2xl space-y-6">
                
                {/* Confidence threshold slider */}
                <div className="bg-card border border-border rounded-xl p-5 shadow-sm space-y-4">
                  <div className="flex justify-between items-center">
                    <label className="text-sm font-semibold text-foreground">Confidence Threshold Gate</label>
                    <span className="text-xs font-bold text-primary bg-primary/10 px-2 py-0.5 rounded">{Math.round(confidenceThreshold * 100)}%</span>
                  </div>
                  <p className="text-xs text-muted-foreground leading-normal">
                    Define the threshold score required for user story auto-validation. Scores below this will flag the story for manual BA review.
                  </p>
                  <input 
                    type="range" 
                    min="0.0" 
                    max="1.0" 
                    step="0.05" 
                    value={confidenceThreshold} 
                    onChange={e => setConfidenceThreshold(parseFloat(e.target.value))}
                    className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
                  />
                </div>

                {/* Max auto-retry attempts */}
                <div className="bg-card border border-border rounded-xl p-5 shadow-sm space-y-4">
                  <label className="text-sm font-semibold text-foreground block">Max Auto-Retry Attempts</label>
                  <p className="text-xs text-muted-foreground leading-normal">
                    The maximum number of times the generator agents will try to self-correct a failed user story before throwing an error.
                  </p>
                  <select 
                    value={maxRetryAttempts}
                    onChange={e => setMaxRetryAttempts(parseInt(e.target.value))}
                    className="bg-background border border-input rounded-xl px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary shadow-sm"
                  >
                    {[1, 2, 3, 4, 5].map(v => (
                      <option key={v} value={v}>{v} {v === 1 ? 'Attempt' : 'Attempts'}</option>
                    ))}
                  </select>
                </div>

                <div className="flex flex-col md:flex-row gap-4 pt-2">
                  <label className={`relative flex-1 cursor-pointer rounded-xl border p-5 shadow-sm focus:outline-none transition-all ${
                    validationMode === 'every-step' ? 'border-primary ring-1 ring-primary bg-primary/5' : 'border-border bg-card hover:bg-accent/50'
                  }`}>
                    <input type="radio" name="validationMode" value="every-step" className="sr-only" checked={validationMode === 'every-step'} onChange={() => setValidationMode('every-step')} />
                    <span className="flex flex-1">
                      <span className="flex flex-col">
                        <span className="block text-sm font-bold text-foreground mb-1 flex items-center gap-2">
                          Step-by-Step Approval
                          <span className="bg-primary/10 text-primary text-[10px] px-1.5 py-0.5 rounded font-bold uppercase tracking-wide">Recommended</span>
                        </span>
                        <span className="flex items-center text-xs text-muted-foreground leading-relaxed">Review and approve at each individual stage of the pipeline for maximum control.</span>
                      </span>
                    </span>
                    <CheckCircle2 className={`absolute top-5 right-5 h-5 w-5 ${validationMode === 'every-step' ? 'text-primary' : 'text-transparent'}`} />
                  </label>

                  <label className={`relative flex-1 cursor-pointer rounded-xl border p-5 shadow-sm focus:outline-none transition-all ${
                    validationMode === 'final' ? 'border-primary ring-1 ring-primary bg-primary/5' : 'border-border bg-card hover:bg-accent/50'
                  }`}>
                    <input type="radio" name="validationMode" value="final" className="sr-only" checked={validationMode === 'final'} onChange={() => setValidationMode('final')} />
                    <span className="flex flex-1">
                      <span className="flex flex-col">
                        <span className="block text-sm font-bold text-foreground mb-1">
                          End-to-End Automatic
                        </span>
                        <span className="flex items-center text-xs text-muted-foreground leading-relaxed">Generate complete epics &amp; stories, then review all at once. The AI checks its own work.</span>
                      </span>
                    </span>
                    <CheckCircle2 className={`absolute top-5 right-5 h-5 w-5 ${validationMode === 'final' ? 'text-primary' : 'text-transparent'}`} />
                  </label>
                </div>
              </div>
            </section>

            {/* Bottom Actions */}
            <div className="pl-9 pt-8 pb-12 flex flex-col gap-4 min-h-[100px]">
              {createError && (
                <div className="flex items-start gap-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 rounded-xl p-4 text-sm max-w-lg">
                  <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
                  <span>{createError}</span>
                </div>
              )}
              {isProcessing ? (
                <div className="w-full max-w-md">
                  <ThinkingIndicator 
                    stages={MOCK_PIPELINE_STAGES.intake} 
                    onComplete={handleProcessingComplete} 
                  />
                </div>
              ) : (
                <Button 
                  type="submit" 
                  size="lg" 
                  className="bg-primary hover:bg-primary/90 text-primary-foreground font-semibold px-8 shadow-sm flex items-center gap-2 h-12 text-sm rounded-xl"
                >
                  Process Document <ArrowRight className="w-4 h-4" />
                </Button>
              )}
            </div>
            
          </form>
        </div>
      </div>
    </div>
  );
}
