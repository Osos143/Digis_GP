import React, { useEffect, useState } from 'react';
import { 
  BarChart3, UploadCloud, Map as MapIcon, ShieldAlert, 
  Settings, History, Search, Bell, User, HelpCircle, 
  Menu, X, CheckCircle, AlertTriangle, AlertCircle, Play, 
  Activity, Zap, FileText, Bot, Download, Filter, ChevronRight, Share2, Upload, File, Send, Mic, MapPin, Layers, Crosshair,
  Eye, EyeOff, Mail, Lock, Shield, Network, Server, Globe,
  Radio, ListChecks, PlusCircle, ArrowLeftRight
} from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { UploadPlanView } from './netpulse/UploadPlanView';
import { PlanningView } from './netpulse/PlanningView';
import { WORKBOOK_MISSING_EVENT } from './netpulse/api';
import { ClashesView } from './netpulse/ClashesView';
import { AssignmentsView } from './netpulse/AssignmentsView';
import { AddSiteView } from './netpulse/AddSiteView';
import { AssistantView } from './netpulse/AssistantView';
import { VoronoiCompareView } from './netpulse/VoronoiCompareView';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell
} from 'recharts';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const PrimaryButtonLike = ({
  onClick,
  children = 'Upload & Plan'
}: {
  onClick: () => void;
  children?: React.ReactNode;
}) => (
  <button
    onClick={onClick}
    className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm transition hover:opacity-90"
  >
    {children}
  </button>
);

const NoWorkbookPrompt = ({ navigate }: { navigate: (v: string) => void }) => (
  <div className="flex flex-col items-center justify-center h-full text-center space-y-4 py-20">
    <UploadCloud className="w-10 h-10 text-gray-400" />
    <h3 className="text-lg font-semibold text-[var(--color-text)]">No workbook loaded yet</h3>
    <p className="text-sm text-gray-500 max-w-sm">Go to Upload &amp; Plan and upload a raw or already-planned .xlsx file to get started.</p>
    <button
      onClick={() => navigate('np-upload')}
      className="flex items-center gap-2 bg-primary text-white px-4 py-2 rounded text-sm font-medium hover:opacity-90 shadow-sm"
    >
      <UploadCloud className="w-4 h-4" /> Go to Upload &amp; Plan
    </button>
  </div>
);
// or simpler, just a plain button instead of a separate component:
// --- Layout Components ---

const SidebarItem = ({ icon: Icon, label, active, onClick }: { icon: any, label: string, active?: boolean, onClick: () => void }) => {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full flex items-center gap-3 px-4 py-2.5 rounded-md transition-colors text-sm font-medium",
        active 
          ? "bg-primary text-primary-foreground" 
          : "text-white hover:bg-white/10 opacity-80 hover:opacity-100"
      )}
    >
      <Icon className="w-4 h-4" />
      {label}
    </button>
  );
};

// --- Mock Data ---

const kpiTrendData = [
  { time: '08:00', value: 92 },
  { time: '09:00', value: 88 },
  { time: '10:00', value: 95 },
  { time: '11:00', value: 78 }, // drop
  { time: '12:00', value: 85 },
  { time: '13:00', value: 91 },
  { time: '14:00', value: 94 },
];

const severityData = [
  { name: 'Critical', value: 15, color: 'var(--color-critical)' },
  { name: 'Warning', value: 35, color: 'var(--color-warning)' },
  { name: 'Minor', value: 50, color: '#FCD34D' },
];

const recentUploads = [
  { id: 'DT_NYC_North_01', date: '2023-10-24 14:30', status: 'Completed', anomalies: 42 },
  { id: 'DT_NYC_South_03', date: '2023-10-24 10:15', status: 'Completed', anomalies: 12 },
  { id: 'DT_BOS_Downtown', date: '2023-10-23 16:45', status: 'Completed', anomalies: 87 },
];

// --- Views ---

const LoginView = ({ navigate }: { navigate: (v: string) => void }) => {
  const [showPassword, setShowPassword] = useState(false);
  const [workspace, setWorkspace] = useState<'anomaly' | 'netpulse'>('anomaly');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [authError, setAuthError] = useState<string | null>(null);

  const ADMIN_EMAIL = 'mosalah@netfix.com';
  const ADMIN_PASSWORD = '8080';

  const enter = () => {
    const normalizedEmail = email.trim().toLowerCase();
    if (normalizedEmail !== ADMIN_EMAIL || password !== ADMIN_PASSWORD) {
      setAuthError('Invalid email or password.');
      return;
    }
    setAuthError(null);
    navigate(workspace === 'netpulse' ? 'np-upload' : 'dashboard');
  };

  return (
    <div className="flex h-screen w-full bg-[#F8FAFC] font-sans overflow-hidden selection:bg-[#2563EB] selection:text-white">
      {/* Left Side - Hero (60%) */}
      <div className="hidden lg:flex flex-col relative w-[60%] bg-[#0F172A] overflow-hidden text-white p-16 justify-center">
        {/* Background Visual Effects */}
        <div className="absolute inset-0 w-full h-full opacity-40 pointer-events-none">
           {/* Abstract glowing orbs */}
           <div className="absolute top-[10%] left-[20%] w-[500px] h-[500px] bg-[#2563EB] rounded-full mix-blend-screen filter blur-[120px] opacity-60"></div>
           <div className="absolute bottom-[10%] right-[10%] w-[400px] h-[400px] bg-[#06B6D4] rounded-full mix-blend-screen filter blur-[120px] opacity-50"></div>
           <div className="absolute top-[40%] right-[30%] w-[300px] h-[300px] bg-[#22C55E] rounded-full mix-blend-screen filter blur-[150px] opacity-30"></div>
           
           {/* Hexagon/Grid Pattern placeholder */}
           <div className="absolute inset-0" style={{ backgroundImage: 'linear-gradient(rgba(255,255,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.05) 1px, transparent 1px)', backgroundSize: '40px 40px' }}></div>
        </div>

        {/* Main Content */}
        <div className="relative z-10 max-w-xl">
           <div className="flex items-center gap-3 mb-8">
             <div className="w-12 h-12 bg-gradient-to-tr from-[#2563EB] to-[#06B6D4] rounded-xl flex items-center justify-center shadow-lg">
               <Activity className="w-7 h-7 text-white" />
             </div>
             <h1 className="text-4xl font-bold text-white tracking-tight">NetFix</h1>
           </div>
           <h2 className="text-4xl font-bold text-white mb-6 leading-[1.15]">
             AI-Powered RAN<br/>Anomaly Detection &<br/>Root Cause Analysis
           </h2>
           <p className="text-lg text-slate-300 mb-10 leading-relaxed max-w-md">
             Analyze drive test datasets, detect network anomalies, identify root causes, and receive AI-powered optimization recommendations in real-time.
           </p>

           <div className="flex gap-6 text-sm font-medium text-slate-400">
              <div className="flex items-center gap-2"><Server className="w-4 h-4"/> 2,345 Active Cells</div>
              <div className="flex items-center gap-2"><AlertOctagon className="w-4 h-4"/> 128 Anomalies Detected</div>
              <div className="flex items-center gap-2"><Globe className="w-4 h-4"/> Global NOC</div>
           </div>
        </div>
      </div>

      {/* Right Side - Login Form (40%) */}
      <div className="flex-1 flex flex-col items-center justify-center p-8 bg-[#F8FAFC] relative">
        <div className="w-full max-w-[440px] bg-white rounded-[14px] shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-[#E2E8F0] p-10 z-10 relative">
          
          {/* Mobile Logo (hidden on desktop) */}
          <div className="flex lg:hidden items-center gap-2 mb-8">
             <div className="w-8 h-8 bg-gradient-to-tr from-[#2563EB] to-[#06B6D4] rounded-lg flex items-center justify-center shadow-md">
               <Activity className="w-5 h-5 text-white" />
             </div>
             <h1 className="text-2xl font-bold text-[#0F172A] tracking-tight">NetFix</h1>
          </div>

          <div className="mb-8">
             <h2 className="text-[28px] font-bold text-[#1E293B] mb-1">Welcome Back</h2>
             <p className="text-[#64748B] text-[15px]">Sign in to continue to NetFix</p>
          </div>
          
          <form onSubmit={(e) => { e.preventDefault(); enter(); }} className="space-y-5">
             {/* Workspace / account selector */}
             <div>
               <label className="block text-[14px] font-medium text-[#1E293B] mb-1.5">Workspace</label>
               <div className="grid grid-cols-2 gap-2 p-1 bg-[#F1F5F9] rounded-[10px]">
                 <button
                   type="button"
                   onClick={() => setWorkspace('anomaly')}
                   className={cn(
                     "flex items-center justify-center gap-2 py-2 rounded-[8px] text-[13px] font-medium transition-all",
                     workspace === 'anomaly' ? "bg-white text-[#1E293B] shadow-sm" : "text-[#64748B] hover:text-[#1E293B]"
                   )}
                 >
                   <ShieldAlert className="w-3.5 h-3.5" /> Drive Test &amp; Anomaly
                 </button>
                 <button
                   type="button"
                   onClick={() => setWorkspace('netpulse')}
                   className={cn(
                     "flex items-center justify-center gap-2 py-2 rounded-[8px] text-[13px] font-medium transition-all",
                     workspace === 'netpulse' ? "bg-white text-[#1E293B] shadow-sm" : "text-[#64748B] hover:text-[#1E293B]"
                   )}
                 >
                   <Radio className="w-3.5 h-3.5" /> 5G Network Planning
                 </button>
               </div>
             </div>

             {/* Email */}
             <div>
               <label className="block text-[14px] font-medium text-[#1E293B] mb-1.5">Email Address</label>
               <div className="relative">
                  <Mail className="absolute left-3.5 top-3 w-5 h-5 text-gray-400" />
                  <input 
                    type="email" 
                    placeholder="engineer@telecom.com" 
                    required
                    value={email}
                    onChange={(e) => {
                      setEmail(e.target.value);
                      if (authError) setAuthError(null);
                    }}
                    className="w-full pl-11 pr-4 py-2.5 text-[15px] bg-[#F8FAFC] border border-[#E2E8F0] rounded-[10px] focus:ring-2 focus:ring-[#2563EB]/20 focus:border-[#2563EB] outline-none transition-all placeholder:text-gray-400 text-[#1E293B]" 
                  />
               </div>
             </div>
             
             {/* Password */}
             <div>
               <label className="block text-[14px] font-medium text-[#1E293B] mb-1.5">Password</label>
               <div className="relative">
                  <Lock className="absolute left-3.5 top-3 w-5 h-5 text-gray-400" />
                  <input 
                    type={showPassword ? "text" : "password"} 
                    placeholder="••••••••" 
                    required
                    value={password}
                    onChange={(e) => {
                      setPassword(e.target.value);
                      if (authError) setAuthError(null);
                    }}
                    className="w-full pl-11 pr-11 py-2.5 text-[15px] bg-[#F8FAFC] border border-[#E2E8F0] rounded-[10px] focus:ring-2 focus:ring-[#2563EB]/20 focus:border-[#2563EB] outline-none transition-all text-[#1E293B]" 
                  />
                  <button 
                    type="button" 
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3.5 top-3 text-gray-400 hover:text-gray-600 transition-colors"
                  >
                    {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
               </div>
             </div>
             
             {/* Options */}
             <div className="flex items-center justify-between pt-1 pb-2">
                <label className="flex items-center gap-2 cursor-pointer group">
                  <div className="relative flex items-center justify-center">
                    <input type="checkbox" className="peer appearance-none w-4 h-4 border border-[#E2E8F0] rounded bg-[#F8FAFC] checked:bg-[#2563EB] checked:border-[#2563EB] transition-colors cursor-pointer" />
                    <svg className="absolute w-3 h-3 text-white pointer-events-none opacity-0 peer-checked:opacity-100 transition-opacity" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M11.6666 3.5L5.24992 9.91667L2.33325 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  </div>
                  <span className="text-[14px] text-[#64748B] group-hover:text-[#1E293B] transition-colors">Remember me</span>
                </label>
                <button type="button" className="text-[14px] font-medium text-[#2563EB] hover:text-[#1D4ED8] transition-colors">
                  Forgot Password?
                </button>
             </div>
             
             {/* Submit Button */}
             <button 
               type="submit" 
               className="w-full py-3 bg-gradient-to-r from-[#2563EB] to-[#06B6D4] text-white rounded-[10px] font-medium text-[16px] hover:shadow-lg hover:shadow-[#2563EB]/20 hover:opacity-90 transition-all active:scale-[0.98]"
             >
               Sign In
             </button>

             {authError && (
               <div className="rounded-[10px] border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700">
                 {authError}
               </div>
             )}
             
             {/* Divider */}
             <div className="flex items-center gap-3 py-2">
                <div className="flex-1 h-px bg-[#E2E8F0]"></div>
                <span className="text-[12px] font-medium text-gray-400 uppercase tracking-wider">OR</span>
                <div className="flex-1 h-px bg-[#E2E8F0]"></div>
             </div>
             
             {/* SSO Button */}
             <button 
               type="button" 
               onClick={enter}
               className="w-full flex items-center justify-center gap-3 py-2.5 bg-white border border-[#E2E8F0] text-[#1E293B] rounded-[10px] font-medium text-[15px] hover:bg-[#F8FAFC] transition-colors shadow-sm"
             >
               <svg className="w-5 h-5" viewBox="0 0 21 21" fill="none" xmlns="http://www.w3.org/2000/svg">
                 <path d="M10 0H0V10H10V0Z" fill="#F25022"/>
                 <path d="M21 0H11V10H21V0Z" fill="#7FBA00"/>
                 <path d="M10 11H0V21H10V11Z" fill="#00A4EF"/>
                 <path d="M21 11H11V21H21V11Z" fill="#FFB900"/>
               </svg>
               Continue with Microsoft
             </button>
          </form>
        </div>

        {/* Bottom Badges & Footer */}
        <div className="absolute bottom-8 flex flex-col items-center gap-4">
          <div className="flex items-center gap-4 px-4 py-2 bg-white rounded-full shadow-sm border border-[#E2E8F0] text-[12px] text-[#64748B] font-medium">
             <span className="flex items-center gap-1.5"><Shield className="w-3.5 h-3.5 text-[#22C55E]"/> Secure Login</span>
             <span className="text-[#E2E8F0]">|</span>
             <span className="flex items-center gap-1.5"><Lock className="w-3.5 h-3.5 text-[#2563EB]"/> JWT Authentication</span>
             <span className="text-[#E2E8F0] hidden sm:inline">|</span>
             <span className="hidden sm:flex items-center gap-1.5"><User className="w-3.5 h-3.5 text-[#06B6D4]"/> Role-based Access</span>
          </div>
          <div className="text-[12px] text-gray-400 flex items-center gap-3">
             <span>NetFix v1.0</span>
             <span>•</span>
             <span>&copy; 2026 NetFix</span>
          </div>
        </div>
      </div>
    </div>
  );
};

// --- Dashboard View ---
const DashboardView = ({ navigate }: { navigate: (v: string) => void }) => {
  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-[var(--color-text)]">Network Overview</h2>
          <p className="text-sm text-gray-500 mt-1">System status and recent anomaly detection metrics.</p>
        </div>
        <div className="flex gap-3">
          <button onClick={() => navigate('upload')} className="flex items-center gap-2 bg-white border border-[var(--color-border)] px-4 py-2 rounded text-sm font-medium hover:bg-gray-50 shadow-sm transition-all">
            <UploadCloud className="w-4 h-4" /> Upload Dataset
          </button>
          <button className="flex items-center gap-2 bg-primary text-primary-foreground px-4 py-2 rounded text-sm font-medium hover:opacity-90 shadow-sm transition-all">
            <Play className="w-4 h-4" /> Run Analysis
          </button>
        </div>
      </div>

      {/* Top Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[
          { label: 'Samples Processed', value: '1.24M', icon: Activity, trend: '+14%', color: 'text-[var(--color-success)]' },
          { label: 'Detected Anomalies', value: '3,492', icon: ShieldAlert, trend: '-5%', color: 'text-[var(--color-success)]' },
          { label: 'Avg Health Score', value: '94.2', icon: CheckCircle, trend: '+0.8', color: 'text-[var(--color-success)]' },
          { label: 'Critical Events', value: '142', icon: AlertOctagon, trend: '+12%', color: 'text-[var(--color-critical)]' },
        ].map((stat, i) => (
          <div key={i} className="bg-[var(--color-surface)] p-5 rounded border border-[var(--color-border)] shadow-sm">
            <div className="flex justify-between items-start mb-4">
              <span className="text-sm font-medium text-gray-500">{stat.label}</span>
              <stat.icon className="w-5 h-5 text-gray-400" />
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold text-[var(--color-text)]">{stat.value}</span>
              <span className={cn("text-xs font-semibold", stat.color)}>{stat.trend}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Chart */}
        <div className="lg:col-span-2 bg-[var(--color-surface)] p-5 rounded border border-[var(--color-border)] shadow-sm">
          <h3 className="text-lg font-semibold mb-6 flex items-center gap-2">
            <Activity className="w-4 h-4 text-primary" />
            Network Health Trend
          </h3>
          <div className="h-[300px] w-full min-h-[300px]">
            <ResponsiveContainer width="100%" height="100%" minHeight={300}>
              <LineChart data={kpiTrendData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--color-border)" />
                <XAxis dataKey="time" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#64748B' }} dy={10} />
                <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#64748B' }} dx={-10} />
                <Tooltip 
                  contentStyle={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)', borderRadius: '4px', fontSize: '12px' }}
                />
                <Line type="monotone" dataKey="value" stroke="var(--color-primary)" strokeWidth={3} dot={{ r: 4, strokeWidth: 2 }} activeDot={{ r: 6 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Breakdown */}
        <div className="bg-[var(--color-surface)] p-5 rounded border border-[var(--color-border)] shadow-sm flex flex-col">
          <h3 className="text-lg font-semibold mb-2">Severity Distribution</h3>
          <div className="flex-1 min-h-[200px] flex items-center justify-center relative w-full">
             <ResponsiveContainer width="100%" height="100%" minHeight={200}>
                <PieChart>
                  <Pie
                    data={severityData}
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={5}
                    dataKey="value"
                    stroke="none"
                  >
                    {severityData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ borderRadius: '4px', border: '1px solid var(--color-border)', fontSize: '12px' }} />
                </PieChart>
             </ResponsiveContainer>
             <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                <span className="text-2xl font-bold">142</span>
                <span className="text-xs text-gray-500 uppercase tracking-wider">Anomalies</span>
             </div>
          </div>
          <div className="flex justify-center gap-4 mt-4">
            {severityData.map(d => (
              <div key={d.name} className="flex items-center gap-1.5 text-xs">
                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: d.color }}></span>
                <span className="text-gray-600">{d.name}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-[var(--color-surface)] rounded border border-[var(--color-border)] shadow-sm overflow-hidden">
          <div className="p-5 border-b border-[var(--color-border)] flex justify-between items-center bg-gray-50/50">
            <h3 className="font-semibold">Recent Uploads</h3>
            <button onClick={() => navigate('history')} className="text-sm text-primary hover:underline">View All</button>
          </div>
          <div className="divide-y divide-[var(--color-border)]">
            {recentUploads.map(upload => (
              <div key={upload.id} className="p-4 flex items-center justify-between hover:bg-gray-50 transition-colors">
                <div className="flex items-center gap-3">
                  <div className="bg-[#E2E8F0] p-2 rounded text-primary">
                    <FileText className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="font-medium text-sm">{upload.id}</div>
                    <div className="text-xs text-gray-500">{upload.date}</div>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <div className="text-xs font-semibold text-gray-700">{upload.anomalies} anomalies</div>
                    <div className="text-xs text-gray-500">{upload.status}</div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-gray-400" />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-[var(--color-surface)] p-5 rounded border border-[var(--color-border)] shadow-sm">
          <div className="flex items-start justify-between mb-6">
            <div>
              <h3 className="font-semibold flex items-center gap-2">
                <Bot className="w-4 h-4 text-primary" />
                AI Insights
              </h3>
              <p className="text-xs text-gray-500 mt-1">Automatically generated from recent analysis runs.</p>
            </div>
          </div>
          <div className="space-y-4">
            <div className="p-4 rounded bg-blue-50 border border-blue-100 flex gap-3 items-start">
              <Zap className="w-4 h-4 text-primary mt-0.5 shrink-0" />
              <div>
                <h4 className="text-sm font-semibold text-blue-900 mb-1">Interference Detected (DT_NYC_North_01)</h4>
                <p className="text-xs text-blue-800 leading-relaxed">
                  High RSRP but poor SINR observed in sector Alpha. Strong correlation with external interference patterns. 
                  Recommended action: Check antenna tilt and physical surroundings for new obstructions.
                </p>
                <div className="mt-3 flex gap-2">
                  <button onClick={() => navigate('results')} className="text-xs bg-white text-primary px-3 py-1.5 rounded border border-blue-200 hover:bg-blue-50 font-medium">View Analysis</button>
                </div>
              </div>
            </div>
            <div className="p-4 rounded bg-gray-50 border border-[var(--color-border)] flex gap-3 items-start opacity-70">
              <Zap className="w-4 h-4 text-gray-500 mt-0.5 shrink-0" />
              <div>
                <h4 className="text-sm font-semibold text-gray-700 mb-1">Handover Failures (DT_BOS_Downtown)</h4>
                <p className="text-xs text-gray-600 leading-relaxed">
                  Multiple intra-frequency handover failures detected between PCI 142 and 145. Likely missing neighbor relation.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

import { FileUp } from 'lucide-react';

const UploadView = ({ navigate }: { navigate: (v: string) => void }) => {
  return (
    <div className="max-w-3xl mx-auto space-y-6 animate-in fade-in duration-300 py-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight text-[var(--color-text)]">Upload Dataset</h2>
        <p className="text-sm text-gray-500 mt-1">Upload Drive Test log files (CSV, Excel, Parquet) for AI analysis.</p>
      </div>

      <div className="bg-[var(--color-surface)] border-2 border-dashed border-[var(--color-border)] rounded-lg p-12 flex flex-col items-center justify-center text-center transition-colors hover:border-primary hover:bg-blue-50/30 cursor-pointer">
        <div className="w-16 h-16 bg-blue-50 rounded-full flex items-center justify-center mb-4">
          <FileUp className="w-8 h-8 text-primary" />
        </div>
        <h3 className="text-lg font-semibold mb-2">Drag & Drop Files Here</h3>
        <p className="text-sm text-gray-500 mb-6 max-w-sm">
          Support for .csv, .xlsx, .parquet formats up to 5GB. Processing time depends on dataset size.
        </p>
        <button className="bg-white border border-[var(--color-border)] text-[var(--color-text)] px-6 py-2.5 rounded font-medium shadow-sm hover:bg-gray-50">
          Browse Files
        </button>
      </div>

      <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded shadow-sm overflow-hidden mt-8">
        <div className="p-4 border-b border-[var(--color-border)] bg-gray-50/50">
          <h3 className="font-medium text-sm">Recent Uploads</h3>
        </div>
        <div className="divide-y divide-[var(--color-border)]">
          {[
            { name: 'NYC_DriveTest_Q3.csv', size: '245 MB', status: 'Ready to configure', date: '2 mins ago' },
            { name: 'Boston_Suburbs.parquet', size: '1.2 GB', status: 'Analysis Complete', date: 'Yesterday' }
          ].map((file, i) => (
            <div key={i} className="p-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <File className="w-4 h-4 text-gray-400" />
                <div>
                  <div className="text-sm font-medium">{file.name}</div>
                  <div className="text-xs text-gray-500">{file.size} • {file.date}</div>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className={cn("text-xs px-2 py-1 rounded-full font-medium", i === 0 ? "bg-blue-100 text-blue-800" : "bg-green-100 text-green-800")}>
                  {file.status}
                </span>
                {i === 0 && (
                   <button onClick={() => navigate('config')} className="text-xs bg-primary text-white px-3 py-1.5 rounded font-medium hover:bg-blue-700">Configure</button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

const ConfigView = ({ navigate }: { navigate: (v: string) => void }) => {
  return (
    <div className="max-w-5xl mx-auto space-y-6 animate-in fade-in duration-300 py-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm text-gray-500 mb-2">
            <span className="hover:text-primary cursor-pointer" onClick={() => navigate('upload')}>Uploads</span>
            <ChevronRight className="w-3 h-3" />
            <span className="font-medium text-gray-900">NYC_DriveTest_Q3.csv</span>
          </div>
          <h2 className="text-2xl font-bold tracking-tight text-[var(--color-text)]">Analysis Configuration</h2>
          <p className="text-sm text-gray-500 mt-1">Define KPI thresholds and anomaly detection sensitivity.</p>
        </div>
        <div className="flex gap-3">
          <button className="bg-white border border-[var(--color-border)] px-4 py-2 rounded text-sm font-medium hover:bg-gray-50 shadow-sm">Save Template</button>
          <button onClick={() => navigate('results')} className="flex items-center gap-2 bg-primary text-white px-4 py-2 rounded text-sm font-medium hover:opacity-90 shadow-sm">
            <Play className="w-4 h-4" /> Start Analysis
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="md:col-span-2 space-y-6">
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded shadow-sm">
            <div className="p-4 border-b border-[var(--color-border)] flex justify-between items-center bg-gray-50/50">
              <h3 className="font-medium">KPI Thresholds</h3>
              <div className="text-xs text-gray-500">3 Active</div>
            </div>
            <div className="p-0">
              <table className="w-full text-sm text-left">
                <thead className="bg-gray-50 text-xs text-gray-500 uppercase border-b border-[var(--color-border)]">
                  <tr>
                    <th className="px-4 py-3 font-medium">KPI</th>
                    <th className="px-4 py-3 font-medium">Unit</th>
                    <th className="px-4 py-3 font-medium text-[var(--color-critical)]">Poor (&lt;)</th>
                    <th className="px-4 py-3 font-medium text-[var(--color-warning)]">Acceptable</th>
                    <th className="px-4 py-3 font-medium text-[var(--color-success)]">Good (&gt;)</th>
                    <th className="px-4 py-3 font-medium text-right">Toggle</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--color-border)]">
                  {[
                    { kpi: 'RSRP', unit: 'dBm', poor: '-110', acc: '-110 to -95', good: '-95' },
                    { kpi: 'SINR', unit: 'dB', poor: '0', acc: '0 to 15', good: '15' },
                    { kpi: 'Throughput DL', unit: 'Mbps', poor: '5', acc: '5 to 25', good: '25' },
                  ].map((row, i) => (
                    <tr key={i} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium">{row.kpi}</td>
                      <td className="px-4 py-3 text-gray-500">{row.unit}</td>
                      <td className="px-4 py-3"><input type="text" defaultValue={row.poor} className="w-16 px-2 py-1 border border-gray-300 rounded text-xs" /></td>
                      <td className="px-4 py-3"><input type="text" defaultValue={row.acc} className="w-24 px-2 py-1 border border-gray-300 rounded text-xs" /></td>
                      <td className="px-4 py-3"><input type="text" defaultValue={row.good} className="w-16 px-2 py-1 border border-gray-300 rounded text-xs" /></td>
                      <td className="px-4 py-3 text-right">
                        <div className="inline-flex items-center cursor-pointer">
                           <div className="w-8 h-4 bg-primary rounded-full relative">
                             <div className="absolute right-0.5 top-0.5 w-3 h-3 bg-white rounded-full"></div>
                           </div>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="p-3 border-t border-[var(--color-border)] bg-gray-50/50">
              <button className="text-sm text-primary font-medium flex items-center gap-1"><Settings className="w-3 h-3" /> Add Custom KPI</button>
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded shadow-sm p-5">
            <h3 className="font-medium mb-4 text-sm">AI Detection Sensitivity</h3>
            <div className="space-y-4">
               <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-gray-500">Anomaly Detection</span>
                    <span className="font-medium">High</span>
                  </div>
                  <input type="range" min="1" max="3" defaultValue="3" className="w-full" />
                  <p className="text-[10px] text-gray-500 mt-1">Higher sensitivity detects more subtle deviations.</p>
               </div>
               <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-gray-500">Correlation Window</span>
                    <span className="font-medium">15 sec</span>
                  </div>
                  <select defaultValue="15 seconds" className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm">
                    <option>5 seconds</option>
                    <option>10 seconds</option>
                    <option>15 seconds</option>
                    <option>30 seconds</option>
                  </select>
               </div>
            </div>
          </div>
          <div className="bg-blue-50 border border-blue-100 rounded shadow-sm p-4">
             <div className="flex gap-2">
               <Bot className="w-4 h-4 text-primary shrink-0" />
               <p className="text-xs text-blue-900">
                 Based on similar datasets, adjusting SINR "Good" threshold to 12dB may reduce false positives in dense urban environments.
               </p>
             </div>
          </div>
        </div>
      </div>
    </div>
  );
};

const ResultsView = ({ navigate }: { navigate: (v: string) => void }) => {
  return (
    <div className="space-y-6 animate-in fade-in duration-300 flex flex-col h-[calc(100vh-80px)]">
      <div className="flex items-center justify-between shrink-0">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-[var(--color-text)]">Analysis Results</h2>
          <p className="text-sm text-gray-500 mt-1">NYC_DriveTest_Q3.csv • Processed 10 mins ago</p>
        </div>
        <div className="flex gap-3">
          <button className="flex items-center gap-2 bg-white border border-[var(--color-border)] px-3 py-2 rounded text-sm font-medium hover:bg-gray-50 shadow-sm">
            <Filter className="w-4 h-4" /> Filter
          </button>
          <button className="flex items-center gap-2 bg-white border border-[var(--color-border)] px-3 py-2 rounded text-sm font-medium hover:bg-gray-50 shadow-sm">
            <Download className="w-4 h-4" /> Export Report
          </button>
        </div>
      </div>

      <div className="flex-1 min-h-0 flex gap-6">
        {/* Main Panel */}
        <div className="flex-1 flex flex-col gap-6 min-w-0">
          <div className="h-64 bg-[var(--color-surface)] border border-[var(--color-border)] rounded shadow-sm shrink-0 relative overflow-hidden">
             {/* Mock Map */}
             <div className="absolute inset-0 bg-[#E2E8F0] opacity-50 flex items-center justify-center">
                <MapIcon className="w-12 h-12 text-gray-400" />
             </div>
             <div className="absolute top-4 left-4 bg-white/90 backdrop-blur border border-gray-200 p-2 rounded shadow-sm text-xs font-medium z-10 flex gap-4">
               <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-[var(--color-critical)]"></div> Critical</div>
               <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-[var(--color-warning)]"></div> Warning</div>
             </div>
             
             {/* Mock map pins */}
             <div className="absolute top-1/3 left-1/4 w-4 h-4 rounded-full bg-[var(--color-critical)]/20 flex items-center justify-center border border-[var(--color-critical)] animate-pulse cursor-pointer" onClick={() => navigate('anomaly')}>
               <div className="w-2 h-2 rounded-full bg-[var(--color-critical)]"></div>
             </div>
             <div className="absolute top-1/2 left-2/3 w-4 h-4 rounded-full bg-[var(--color-warning)]/20 flex items-center justify-center border border-[var(--color-warning)]">
               <div className="w-2 h-2 rounded-full bg-[var(--color-warning)]"></div>
             </div>
          </div>

          <div className="flex-1 bg-[var(--color-surface)] border border-[var(--color-border)] rounded shadow-sm flex flex-col min-h-0">
            <div className="p-3 border-b border-[var(--color-border)] bg-gray-50/50 flex justify-between items-center">
              <h3 className="text-sm font-semibold">Detected Anomalies (142)</h3>
              <div className="relative">
                <Search className="w-4 h-4 absolute left-2.5 top-2 text-gray-400" />
                <input type="text" placeholder="Search Cell ID..." className="pl-8 pr-3 py-1.5 text-sm border border-gray-300 rounded focus:outline-none focus:border-primary w-64" />
              </div>
            </div>
            <div className="flex-1 overflow-auto">
              <table className="w-full text-sm text-left">
                <thead className="bg-gray-50 text-xs text-gray-500 uppercase sticky top-0 border-b border-[var(--color-border)] shadow-sm">
                  <tr>
                    <th className="px-4 py-3 font-medium">Anomaly Type</th>
                    <th className="px-4 py-3 font-medium">Severity</th>
                    <th className="px-4 py-3 font-medium">Cell ID</th>
                    <th className="px-4 py-3 font-medium">Time</th>
                    <th className="px-4 py-3 font-medium">Confidence</th>
                    <th className="px-4 py-3"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--color-border)]">
                  {[
                    { type: 'Cross-Feeder / Interference', severity: 'Critical', cell: 'LC_NYC_14A', time: '14:23:41', conf: '94%' },
                    { type: 'Missing Neighbor Relation', severity: 'Warning', cell: 'LC_NYC_09B', time: '14:25:12', conf: '88%' },
                    { type: 'Coverage Hole', severity: 'Critical', cell: 'LC_NYC_22C', time: '14:31:05', conf: '97%' },
                    { type: 'Overshoot', severity: 'Minor', cell: 'LC_NYC_14A', time: '14:35:22', conf: '72%' },
                  ].map((row, i) => (
                    <tr key={i} className="hover:bg-gray-50 cursor-pointer group" onClick={() => navigate('anomaly')}>
                      <td className="px-4 py-3 font-medium text-gray-900 group-hover:text-primary transition-colors">{row.type}</td>
                      <td className="px-4 py-3">
                        <span className={cn(
                          "px-2 py-0.5 rounded text-xs font-medium border",
                          row.severity === 'Critical' ? "bg-red-50 text-red-700 border-red-200" :
                          row.severity === 'Warning' ? "bg-amber-50 text-amber-700 border-amber-200" :
                          "bg-yellow-50 text-yellow-800 border-yellow-200"
                        )}>
                          {row.severity}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs">{row.cell}</td>
                      <td className="px-4 py-3 text-gray-500">{row.time}</td>
                      <td className="px-4 py-3 text-gray-500">{row.conf}</td>
                      <td className="px-4 py-3 text-right">
                        <button className="text-gray-400 hover:text-primary"><ChevronRight className="w-4 h-4" /></button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

const AnomalyDetailView = ({ navigate }: { navigate: (v: string) => void }) => {
  return (
    <div className="space-y-6 animate-in fade-in duration-300 pb-10">
       <div className="flex items-center gap-2 text-sm text-gray-500 mb-2">
          <span className="hover:text-primary cursor-pointer" onClick={() => navigate('results')}>Results</span>
          <ChevronRight className="w-3 h-3" />
          <span className="font-medium text-gray-900">ANM-942</span>
        </div>
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <h2 className="text-2xl font-bold tracking-tight text-[var(--color-text)]">Cross-Feeder / Interference</h2>
            <span className="bg-red-50 text-red-700 border border-red-200 px-2 py-0.5 rounded text-xs font-semibold">Critical</span>
          </div>
          <p className="text-sm text-gray-500">Cell ID: <span className="font-mono text-gray-800">LC_NYC_14A</span> • Oct 24, 14:23:41 • Conf: 94%</p>
        </div>
        <div className="flex gap-3">
           <button className="flex items-center gap-2 bg-white border border-[var(--color-border)] px-4 py-2 rounded text-sm font-medium hover:bg-gray-50 shadow-sm">
            <Share2 className="w-4 h-4" /> Share
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded shadow-sm p-6">
            <h3 className="text-lg font-semibold mb-4 border-b pb-2">KPI Evidence</h3>
            <div className="grid grid-cols-2 gap-4 mb-6">
               <div className="p-4 bg-gray-50 rounded border border-[var(--color-border)]">
                 <div className="text-sm text-gray-500 mb-1">RSRP</div>
                 <div className="text-xl font-bold text-[var(--color-success)]">-82 dBm</div>
                 <div className="text-xs text-gray-500 mt-1">Excellent coverage</div>
               </div>
               <div className="p-4 bg-red-50 rounded border border-red-100">
                 <div className="text-sm text-red-600 mb-1">SINR</div>
                 <div className="text-xl font-bold text-[var(--color-critical)]">-2.4 dB</div>
                 <div className="text-xs text-red-600 mt-1">Severely degraded</div>
               </div>
            </div>
            
            <h4 className="font-medium text-sm mb-3">Time-series Trend</h4>
            <div className="h-48 w-full min-h-[192px]">
              <ResponsiveContainer width="100%" height="100%" minHeight={192}>
                <LineChart data={[
                  { time: '14:23:30', rsrp: -85, sinr: 12 },
                  { time: '14:23:35', rsrp: -84, sinr: 10 },
                  { time: '14:23:40', rsrp: -82, sinr: -2 }, // anomaly
                  { time: '14:23:45', rsrp: -81, sinr: -3 },
                  { time: '14:23:50', rsrp: -83, sinr: -1 },
                ]} margin={{ top: 5, right: 20, bottom: 5, left: -20 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="time" tick={{fontSize: 10}} />
                  <YAxis yAxisId="left" tick={{fontSize: 10}} />
                  <YAxis yAxisId="right" orientation="right" tick={{fontSize: 10}} />
                  <Tooltip />
                  <Line yAxisId="left" type="stepAfter" dataKey="rsrp" stroke="#2E7D32" strokeWidth={2} dot={false} />
                  <Line yAxisId="right" type="stepAfter" dataKey="sinr" stroke="#D32F2F" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="flex gap-4 mt-2 justify-center text-xs text-gray-500">
              <span className="flex items-center gap-1"><div className="w-3 h-0.5 bg-[#2E7D32]"></div> RSRP</span>
              <span className="flex items-center gap-1"><div className="w-3 h-0.5 bg-[#D32F2F]"></div> SINR</span>
            </div>
          </div>

          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded shadow-sm overflow-hidden">
             <div className="p-4 border-b border-[var(--color-border)] bg-gray-50/50 flex items-center gap-2">
                <Bot className="w-5 h-5 text-primary" />
                <h3 className="font-semibold text-[var(--color-text)]">AI Root Cause Analysis</h3>
             </div>
             <div className="p-6">
               <p className="text-sm text-gray-700 leading-relaxed mb-4">
                 The sharp drop in SINR accompanied by strong RSRP strongly indicates interference. 
                 Given the specific sector and the lack of handovers prior to the drop, this is characteristic of either external interference or a crossed feeder cable where the UE is receiving a strong signal from an unintended antenna port.
               </p>
               <h4 className="text-sm font-semibold mb-3">Recommended Actions</h4>
               <ul className="space-y-3">
                 <li className="flex gap-3 text-sm items-start">
                   <div className="bg-blue-50 text-blue-700 w-6 h-6 rounded-full flex items-center justify-center shrink-0 mt-0.5 font-bold text-xs">1</div>
                   <div>
                     <span className="font-medium block">Physical Site Audit</span>
                     <span className="text-gray-500">Dispatch field technician to verify feeder cable connections at the RRU and antenna ports.</span>
                   </div>
                 </li>
                 <li className="flex gap-3 text-sm items-start">
                   <div className="bg-blue-50 text-blue-700 w-6 h-6 rounded-full flex items-center justify-center shrink-0 mt-0.5 font-bold text-xs">2</div>
                   <div>
                     <span className="font-medium block">Interference Hunting</span>
                     <span className="text-gray-500">If physical connections are correct, initiate spectrum analyzer trace on uplink frequencies.</span>
                   </div>
                 </li>
               </ul>
             </div>
          </div>
        </div>

        <div className="space-y-6">
           <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded shadow-sm p-4">
             <h3 className="font-semibold text-sm mb-3">Location Context</h3>
             <div className="h-40 bg-[#E2E8F0] rounded mb-3 flex items-center justify-center overflow-hidden relative">
               <MapIcon className="w-8 h-8 text-gray-400 absolute" />
               <div className="absolute inset-0 bg-gradient-to-tr from-transparent to-white/20"></div>
             </div>
             <div className="text-xs text-gray-500 space-y-2">
                <div className="flex justify-between"><span>Lat/Long:</span> <span className="font-mono text-gray-800">40.7128, -74.0060</span></div>
                <div className="flex justify-between"><span>Speed:</span> <span className="font-mono text-gray-800">45 km/h</span></div>
                <div className="flex justify-between"><span>Distance to cell:</span> <span className="font-mono text-gray-800">420m</span></div>
             </div>
           </div>
        </div>
      </div>
    </div>
  );
};

// --- Placeholder View ---
const PlaceholderView = ({ title, icon: Icon, description }: { title: string, icon: any, description: string }) => (
  <div className="flex flex-col items-center justify-center h-full text-center space-y-4 animate-in fade-in duration-300">
    <div className="w-16 h-16 bg-blue-50 text-primary rounded-full flex items-center justify-center mb-2">
      <Icon className="w-8 h-8" />
    </div>
    <h2 className="text-2xl font-bold text-[var(--color-text)]">{title}</h2>
    <p className="text-gray-500 max-w-md">{description}</p>
    <div className="text-sm text-gray-500 mt-6 border border-dashed border-gray-300 p-4 rounded bg-[var(--color-surface)] shadow-sm">
      This view is currently a placeholder. I can build out the full functionality for this page upon request!
    </div>
  </div>
);

const MapView = () => {
  return (
    <div className="flex flex-col h-[calc(100vh-80px)] animate-in fade-in duration-300 -m-6">
      <div className="bg-white border-b border-[var(--color-border)] p-4 flex justify-between items-center z-10 shadow-sm relative">
        <div>
          <h2 className="text-lg font-bold">Interactive Map</h2>
          <p className="text-xs text-gray-500">Showing DT_NYC_North_01</p>
        </div>
        <div className="flex gap-2">
           <button className="flex items-center gap-2 bg-gray-50 border border-[var(--color-border)] px-3 py-1.5 rounded text-sm font-medium hover:bg-gray-100"><Layers className="w-4 h-4"/> Layers</button>
           <button className="flex items-center gap-2 bg-gray-50 border border-[var(--color-border)] px-3 py-1.5 rounded text-sm font-medium hover:bg-gray-100"><Filter className="w-4 h-4"/> Filters</button>
        </div>
      </div>
      <div className="flex-1 bg-[#E2E8F0] relative overflow-hidden flex items-center justify-center">
         {/* Fake Map Grid Background */}
         <div className="absolute inset-0 opacity-20" style={{ backgroundImage: 'linear-gradient(#94a3b8 1px, transparent 1px), linear-gradient(90deg, #94a3b8 1px, transparent 1px)', backgroundSize: '40px 40px' }}></div>
         
         <MapIcon className="w-24 h-24 text-gray-400 absolute opacity-50" />
         
         {/* Fake Route */}
         <svg className="absolute inset-0 w-full h-full pointer-events-none">
           <path d="M 200 300 Q 400 200 500 400 T 800 300" fill="transparent" stroke="rgba(0,0,0,0.2)" strokeWidth="6" strokeDasharray="10 5" />
           <path d="M 200 300 Q 400 200 500 400 T 800 300" fill="transparent" stroke="#2E7D32" strokeWidth="4" />
         </svg>

         {/* Pins */}
         <div className="absolute top-[380px] left-[480px] w-6 h-6 bg-[var(--color-critical)] rounded-full border-2 border-white shadow-lg flex items-center justify-center animate-bounce cursor-pointer">
            <Crosshair className="w-3 h-3 text-white" />
         </div>
         <div className="absolute top-[280px] left-[780px] w-5 h-5 bg-[var(--color-warning)] rounded-full border-2 border-white shadow-lg cursor-pointer"></div>
         <div className="absolute top-[320px] left-[220px] w-4 h-4 bg-[#FCD34D] rounded-full border-2 border-white shadow-lg cursor-pointer"></div>

         {/* Floating panel */}
         <div className="absolute top-4 right-4 w-80 bg-white/95 backdrop-blur rounded shadow-lg border border-[var(--color-border)] overflow-hidden">
            <div className="p-3 border-b border-[var(--color-border)] bg-gray-50 flex justify-between items-center">
               <span className="font-semibold text-sm">Selected Anomaly</span>
               <X className="w-4 h-4 text-gray-400 cursor-pointer" />
            </div>
            <div className="p-4 space-y-3">
               <div className="flex items-center gap-2">
                 <span className="bg-red-50 text-red-700 px-2 py-0.5 rounded text-[10px] font-bold border border-red-200 uppercase">Critical</span>
                 <span className="font-medium text-sm">Interference</span>
               </div>
               <div className="text-xs text-gray-600">
                 Cell ID: <strong>LC_NYC_14A</strong><br/>
                 Time: 14:23:41
               </div>
               <div className="grid grid-cols-2 gap-2 text-xs">
                 <div className="bg-gray-50 p-2 rounded border border-gray-200">
                   <div className="text-gray-500">RSRP</div>
                   <div className="font-semibold text-[var(--color-success)]">-82 dBm</div>
                 </div>
                 <div className="bg-gray-50 p-2 rounded border border-gray-200">
                   <div className="text-gray-500">SINR</div>
                   <div className="font-semibold text-[var(--color-critical)]">-2.4 dB</div>
                 </div>
               </div>
               <button className="w-full bg-primary text-white text-xs py-2 rounded font-medium mt-2 hover:bg-blue-700">View Details</button>
            </div>
         </div>
      </div>
    </div>
  );
};

const StatisticsView = () => {
  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-[var(--color-text)]">Statistics & Trends</h2>
          <p className="text-sm text-gray-500 mt-1">Aggregate metrics across all recent drive test sessions.</p>
        </div>
        <select className="border border-gray-300 rounded px-3 py-1.5 text-sm bg-white shadow-sm">
          <option>Last 7 Days</option>
          <option>Last 30 Days</option>
          <option>This Quarter</option>
        </select>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-[var(--color-surface)] p-5 rounded border border-[var(--color-border)] shadow-sm">
          <h3 className="text-sm font-semibold mb-4 border-b pb-2">Anomaly Distribution by Type</h3>
          <div className="h-64 w-full min-h-[256px]">
            <ResponsiveContainer width="100%" height="100%" minHeight={256}>
              <BarChart data={[
                { name: 'Interference', count: 45 },
                { name: 'Missing Neighbor', count: 82 },
                { name: 'Coverage Hole', count: 31 },
                { name: 'Overshoot', count: 24 },
                { name: 'Handover Fail', count: 56 },
              ]} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" tick={{fontSize: 10}} interval={0} angle={-25} textAnchor="end" height={50} />
                <YAxis tick={{fontSize: 10}} />
                <Tooltip cursor={{fill: '#f4f6f8'}} />
                <Bar dataKey="count" fill="var(--color-primary)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-[var(--color-surface)] p-5 rounded border border-[var(--color-border)] shadow-sm">
          <h3 className="text-sm font-semibold mb-4 border-b pb-2">RSRP vs SINR Scatter (Sample)</h3>
          <div className="h-64 flex items-center justify-center bg-gray-50 rounded border border-dashed border-gray-300">
             <div className="text-center">
               <Activity className="w-8 h-8 text-gray-400 mx-auto mb-2" />
               <p className="text-xs text-gray-500">Scatter correlation plot rendering requires more data points.</p>
             </div>
          </div>
        </div>

        <div className="bg-[var(--color-surface)] p-5 rounded border border-[var(--color-border)] shadow-sm lg:col-span-2">
          <h3 className="text-sm font-semibold mb-4 border-b pb-2">Weekly Anomaly Trend</h3>
          <div className="h-64 w-full min-h-[256px]">
            <ResponsiveContainer width="100%" height="100%" minHeight={256}>
              <LineChart data={[
                { date: 'Mon', critical: 12, warning: 30 },
                { date: 'Tue', critical: 18, warning: 45 },
                { date: 'Wed', critical: 5, warning: 20 },
                { date: 'Thu', critical: 22, warning: 50 },
                { date: 'Fri', critical: 9, warning: 25 },
                { date: 'Sat', critical: 4, warning: 15 },
                { date: 'Sun', critical: 2, warning: 10 },
              ]} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tick={{fontSize: 12}} />
                <YAxis tick={{fontSize: 12}} />
                <Tooltip />
                <Line type="monotone" dataKey="critical" stroke="var(--color-critical)" strokeWidth={2} />
                <Line type="monotone" dataKey="warning" stroke="var(--color-warning)" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
};

const ReportsView = () => {
  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-[var(--color-text)]">Reports</h2>
          <p className="text-sm text-gray-500 mt-1">Generated PDF reports from analysis sessions.</p>
        </div>
        <button className="flex items-center gap-2 bg-primary text-white px-4 py-2 rounded text-sm font-medium hover:bg-blue-700 shadow-sm">
          <FileText className="w-4 h-4" /> New Report
        </button>
      </div>

      <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded shadow-sm overflow-hidden">
        <table className="w-full text-sm text-left">
          <thead className="bg-gray-50 text-xs text-gray-500 uppercase border-b border-[var(--color-border)]">
            <tr>
              <th className="px-6 py-4 font-medium">Report Name</th>
              <th className="px-6 py-4 font-medium">Dataset</th>
              <th className="px-6 py-4 font-medium">Date Generated</th>
              <th className="px-6 py-4 font-medium">Size</th>
              <th className="px-6 py-4"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-border)]">
            {[
              { name: 'NYC North Optimization Audit', dataset: 'DT_NYC_North_01', date: 'Oct 24, 2023', size: '2.4 MB' },
              { name: 'Boston Handover Analysis', dataset: 'DT_BOS_Downtown', date: 'Oct 23, 2023', size: '1.8 MB' },
              { name: 'Weekly Executive Summary', dataset: 'Multiple', date: 'Oct 20, 2023', size: '4.1 MB' },
            ].map((report, i) => (
              <tr key={i} className="hover:bg-gray-50">
                <td className="px-6 py-4 font-medium flex items-center gap-3">
                  <div className="bg-red-100 text-red-600 p-1.5 rounded"><FileText className="w-4 h-4"/></div>
                  {report.name}
                </td>
                <td className="px-6 py-4 text-gray-500">{report.dataset}</td>
                <td className="px-6 py-4 text-gray-500">{report.date}</td>
                <td className="px-6 py-4 text-gray-500">{report.size}</td>
                <td className="px-6 py-4 text-right">
                  <button className="text-primary font-medium hover:underline flex items-center gap-1 justify-end w-full">
                    <Download className="w-4 h-4" /> Download
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const AIAssistantView = () => {
  return (
    <div className="flex flex-col h-[calc(100vh-100px)] animate-in fade-in duration-300 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg shadow-sm overflow-hidden">
      <div className="bg-gray-50 border-b border-[var(--color-border)] p-4 flex items-center gap-3 shrink-0">
         <div className="w-10 h-10 bg-primary/10 rounded-full flex items-center justify-center">
            <Bot className="w-5 h-5 text-primary" />
         </div>
         <div>
           <h2 className="font-bold text-sm">NetFix AI Assistant</h2>
           <p className="text-xs text-gray-500">Ask about anomalies, datasets, or optimization actions</p>
         </div>
      </div>
      
      <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-white">
         <div className="flex gap-4">
            <div className="w-8 h-8 bg-primary/10 rounded-full flex items-center justify-center shrink-0">
               <Bot className="w-4 h-4 text-primary" />
            </div>
            <div className="bg-gray-50 border border-gray-100 p-4 rounded-lg rounded-tl-none max-w-2xl text-sm text-gray-800 leading-relaxed shadow-sm">
               Hello! I'm your NetFix AI assistant. I've analyzed the recent <strong>DT_NYC_North_01</strong> dataset. I noticed a high frequency of interference-related anomalies in the Alpha sector. Would you like me to summarize the root causes or generate a mitigation plan?
            </div>
         </div>

         <div className="flex gap-4 flex-row-reverse">
            <div className="w-8 h-8 bg-gray-200 rounded-full flex items-center justify-center shrink-0">
               <User className="w-4 h-4 text-gray-600" />
            </div>
            <div className="bg-primary text-white p-4 rounded-lg rounded-tr-none max-w-2xl text-sm leading-relaxed shadow-sm">
               Yes, please summarize the root causes for the interference in sector Alpha.
            </div>
         </div>

         <div className="flex gap-4">
            <div className="w-8 h-8 bg-primary/10 rounded-full flex items-center justify-center shrink-0">
               <Bot className="w-4 h-4 text-primary" />
            </div>
            <div className="bg-gray-50 border border-gray-100 p-4 rounded-lg rounded-tl-none max-w-2xl text-sm text-gray-800 leading-relaxed shadow-sm">
               Based on the correlation of high RSRP (&gt; -85 dBm) and severely degraded SINR (&lt; 0 dB) without corresponding handover attempts, the AI models indicate an 88% probability of <strong>External Uplink Interference</strong> and a 12% probability of a <strong>Crossed Feeder Cable</strong>. 
               <br/><br/>
               I recommend dispatching a field tech to perform a physical site audit on cell <strong>LC_NYC_14A</strong> before adjusting any tilt parameters.
            </div>
         </div>
      </div>

      <div className="p-4 border-t border-[var(--color-border)] bg-white shrink-0">
         <div className="relative">
            <input 
              type="text" 
              placeholder="Ask a question..." 
              className="w-full pl-4 pr-12 py-3 bg-gray-50 border border-gray-300 rounded-full text-sm focus:outline-none focus:ring-1 focus:ring-primary"
            />
            <button className="absolute right-2 top-1.5 w-9 h-9 bg-primary text-white rounded-full flex items-center justify-center hover:bg-blue-700 transition-colors">
               <Send className="w-4 h-4 ml-0.5" />
            </button>
         </div>
      </div>
    </div>
  );
};

const HistoryView = () => {
  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-[var(--color-text)]">Dataset History</h2>
          <p className="text-sm text-gray-500 mt-1">Audit log of all uploaded datasets and their status.</p>
        </div>
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-2 text-gray-400" />
          <input type="text" placeholder="Search datasets..." className="pl-9 pr-4 py-1.5 border border-gray-300 rounded text-sm w-64" />
        </div>
      </div>

      <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded shadow-sm overflow-hidden">
        <table className="w-full text-sm text-left">
          <thead className="bg-gray-50 text-xs text-gray-500 uppercase border-b border-[var(--color-border)]">
            <tr>
              <th className="px-6 py-4 font-medium">Dataset Name</th>
              <th className="px-6 py-4 font-medium">Uploaded By</th>
              <th className="px-6 py-4 font-medium">Upload Date</th>
              <th className="px-6 py-4 font-medium">Status</th>
              <th className="px-6 py-4 font-medium">Anomalies</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-border)]">
            {[
              { name: 'DT_NYC_North_01.csv', user: 'John Doe', date: 'Oct 24, 2023 14:30', status: 'Analysis Complete', anomalies: 42 },
              { name: 'DT_NYC_South_03.parquet', user: 'Jane Smith', date: 'Oct 24, 2023 10:15', status: 'Analysis Complete', anomalies: 12 },
              { name: 'DT_BOS_Downtown.xlsx', user: 'John Doe', date: 'Oct 23, 2023 16:45', status: 'Analysis Complete', anomalies: 87 },
              { name: 'DT_CHI_Suburbs.csv', user: 'Admin', date: 'Oct 22, 2023 09:00', status: 'Archived', anomalies: 15 },
            ].map((row, i) => (
              <tr key={i} className="hover:bg-gray-50">
                <td className="px-6 py-4 font-medium text-gray-900">{row.name}</td>
                <td className="px-6 py-4 text-gray-500">{row.user}</td>
                <td className="px-6 py-4 text-gray-500">{row.date}</td>
                <td className="px-6 py-4">
                  <span className={cn(
                    "px-2 py-1 rounded-full text-xs font-medium",
                    row.status === 'Analysis Complete' ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-800"
                  )}>
                    {row.status}
                  </span>
                </td>
                <td className="px-6 py-4 text-gray-500 font-medium">{row.anomalies}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const SettingsView = () => {
  return (
    <div className="max-w-4xl space-y-6 animate-in fade-in duration-300">
      <div>
        <h2 className="text-2xl font-bold tracking-tight text-[var(--color-text)]">Settings</h2>
        <p className="text-sm text-gray-500 mt-1">Manage platform configurations and global preferences.</p>
      </div>

      <div className="flex gap-6">
        <div className="w-48 shrink-0 flex flex-col gap-1">
          <button className="text-left px-3 py-2 bg-gray-100 text-primary font-medium rounded text-sm">General</button>
          <button className="text-left px-3 py-2 text-gray-600 hover:bg-gray-50 rounded text-sm">Default Thresholds</button>
          <button className="text-left px-3 py-2 text-gray-600 hover:bg-gray-50 rounded text-sm">User Management</button>
          <button className="text-left px-3 py-2 text-gray-600 hover:bg-gray-50 rounded text-sm">Integrations</button>
        </div>
        
        <div className="flex-1 bg-[var(--color-surface)] border border-[var(--color-border)] rounded shadow-sm p-6 space-y-6">
           <div>
             <h3 className="text-lg font-semibold mb-4">General Settings</h3>
             <div className="space-y-4">
               <div>
                 <label className="block text-sm font-medium text-gray-700 mb-1">Platform Name</label>
                 <input type="text" defaultValue="NetFix Enterprise" className="w-full max-w-md border border-gray-300 rounded px-3 py-2 text-sm" />
               </div>
               <div>
                 <label className="block text-sm font-medium text-gray-700 mb-1">Timezone</label>
                 <select defaultValue="EST (Eastern Standard Time)" className="w-full max-w-md border border-gray-300 rounded px-3 py-2 text-sm">
                   <option>UTC (Coordinated Universal Time)</option>
                   <option>EST (Eastern Standard Time)</option>
                 </select>
               </div>
               <div className="flex items-center gap-3 pt-2">
                 <input type="checkbox" id="darkmode" className="w-4 h-4 rounded text-primary focus:ring-primary border-gray-300" />
                 <label htmlFor="darkmode" className="text-sm text-gray-700">Enable Dark Mode automatically</label>
               </div>
             </div>
           </div>
           <div className="pt-4 border-t border-[var(--color-border)] flex justify-end">
             <button className="bg-primary text-white px-4 py-2 rounded text-sm font-medium shadow-sm hover:bg-blue-700">Save Changes</button>
           </div>
        </div>
      </div>
    </div>
  );
};

// --- App Root ---

import { AlertOctagon } from 'lucide-react';

const NETPULSE_TABS = ['np-upload', 'np-planning', 'np-clashes', 'np-assignments', 'np-addsite', 'np-assistant', 'np-voronoi'] as const;
type NetPulseTab = typeof NETPULSE_TABS[number];

export default function App() {
  const [currentView, setCurrentView] = useState<string>(() => localStorage.getItem('netpulse-current-view') || 'login');
  const [npWorkbook, setNpWorkbook] = useState<string>(() => localStorage.getItem('netpulse-workbook') || '');
  const isNetPulse = currentView.startsWith('np-');

  useEffect(() => {
    localStorage.setItem('netpulse-current-view', currentView);
  }, [currentView]);

  useEffect(() => {
    localStorage.setItem('netpulse-workbook', npWorkbook);
  }, [npWorkbook]);

  useEffect(() => {
    const onWorkbookMissing = () => {
      setNpWorkbook('');
      setCurrentView('np-upload');
    };
    window.addEventListener(WORKBOOK_MISSING_EVENT, onWorkbookMissing);
    return () => window.removeEventListener(WORKBOOK_MISSING_EVENT, onWorkbookMissing);
  }, []);

  const renderView = () => {
    switch (currentView) {
      case 'login': return null; // Handled by early return below
      case 'dashboard': return <DashboardView navigate={setCurrentView} />;
      case 'upload': return <UploadView navigate={setCurrentView} />;
      case 'config': return <ConfigView navigate={setCurrentView} />;
      case 'results': return <ResultsView navigate={setCurrentView} />;
      case 'anomaly': return <AnomalyDetailView navigate={setCurrentView} />;
      case 'map': return <MapView />;
      case 'statistics': return <StatisticsView />;
      case 'reports': return <ReportsView />;
      case 'ai': return <AIAssistantView />;
      case 'history': return <HistoryView />;
      case 'settings': return <SettingsView />;
      default: return <DashboardView navigate={setCurrentView} />;
    }
  };

  const renderNetPulseTab = (tab: NetPulseTab) => {
    switch (tab) {
      case 'np-upload':
        return <UploadPlanView workbook={npWorkbook} setWorkbook={setNpWorkbook} />;
      case 'np-planning':
        return npWorkbook
          ? <PlanningView workbook={npWorkbook} setWorkbook={setNpWorkbook} />
          : <NoWorkbookPrompt navigate={setCurrentView} />;
      case 'np-clashes':
        return npWorkbook ? <ClashesView workbook={npWorkbook} /> : <NoWorkbookPrompt navigate={setCurrentView} />;
      case 'np-assignments':
        return npWorkbook ? <AssignmentsView workbook={npWorkbook} /> : <NoWorkbookPrompt navigate={setCurrentView} />;
      case 'np-addsite':
        return npWorkbook
          ? <AddSiteView workbook={npWorkbook} setWorkbook={setNpWorkbook} />
          : <NoWorkbookPrompt navigate={setCurrentView} />;
      case 'np-assistant':
        return npWorkbook ? <AssistantView workbook={npWorkbook} /> : <NoWorkbookPrompt navigate={setCurrentView} />;
      case 'np-voronoi':
        return npWorkbook
          ? <VoronoiCompareView workbook={npWorkbook} navigate={setCurrentView} />
          : <NoWorkbookPrompt navigate={setCurrentView} />;
    }
  };

  const renderNetPulseContent = () => {
    if (!npWorkbook) {
      return currentView === 'np-upload'
        ? renderNetPulseTab('np-upload')
        : <NoWorkbookPrompt navigate={setCurrentView} />;
    }

    return (
      <>
        <div className={cn(currentView === 'np-assistant' ? 'block h-full' : 'hidden')}>
          <AssistantView workbook={npWorkbook} />
        </div>
        {currentView !== 'np-assistant' && renderNetPulseTab(currentView as NetPulseTab)}
      </>
    );
  };

  if (currentView === 'login') {
    return <LoginView navigate={setCurrentView} />;
  }

  return (
    <div className="flex h-screen bg-[var(--color-background)] font-sans text-[var(--color-text)] overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 bg-[#111827] text-gray-300 flex flex-col shadow-xl shrink-0 z-20 relative">
        <div className="h-16 flex items-center px-6 border-b border-gray-800 shrink-0">
          <div className="flex items-center gap-2 text-white font-bold text-xl tracking-tight">
             <Activity className="w-6 h-6 text-[#00ACC1]" /> NetFix
          </div>
        </div>
        {isNetPulse ? (
          <>
            <div className="flex-1 overflow-y-auto py-6 px-3 space-y-1">
              <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-3">5G Planning &middot; PCI/RSI/Mod4</div>
              <SidebarItem icon={UploadCloud} label="Upload & Plan" active={currentView === 'np-upload'} onClick={() => setCurrentView('np-upload')} />
              <SidebarItem icon={Radio} label="Planning" active={currentView === 'np-planning'} onClick={() => setCurrentView('np-planning')} />
              <SidebarItem icon={Zap} label="Clashes" active={currentView === 'np-clashes'} onClick={() => setCurrentView('np-clashes')} />
              <SidebarItem icon={ListChecks} label="Assignments" active={currentView === 'np-assignments'} onClick={() => setCurrentView('np-assignments')} />
              <SidebarItem icon={PlusCircle} label="Add Site" active={currentView === 'np-addsite'} onClick={() => setCurrentView('np-addsite')} />
              <SidebarItem icon={Bot} label="AI Agent" active={currentView === 'np-assistant'} onClick={() => setCurrentView('np-assistant')} />
              <SidebarItem icon={History} label="Voronoi Compare" active={currentView === 'np-voronoi'} onClick={() => setCurrentView('np-voronoi')} />
              
              <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 mt-6 px-3">System</div>
              <SidebarItem icon={ArrowLeftRight} label="Switch Workspace" active={false} onClick={() => setCurrentView('login')} />
            </div>
            <div className="p-4 border-t border-gray-800 text-white">
               <div className="flex items-center gap-3 px-2 py-2">
                 <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center text-primary font-bold text-sm">
                   MS
                 </div>
                 <div>
                   <div className="text-sm font-medium text-white">Mohamed Salah</div>
                   <div className="text-xs text-white">5G Planning Engineer</div>
                 </div>
               </div>
            </div>
          </>
        ) : (
          <>
            <div className="flex-1 overflow-y-auto py-6 px-3 space-y-1">
              <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-3">Analysis</div>
              <SidebarItem icon={BarChart3} label="Dashboard" active={currentView === 'dashboard'} onClick={() => setCurrentView('dashboard')} />
              <SidebarItem icon={UploadCloud} label="Upload Dataset" active={currentView === 'upload' || currentView === 'config'} onClick={() => setCurrentView('upload')} />
              <SidebarItem icon={ShieldAlert} label="Results" active={currentView === 'results' || currentView === 'anomaly'} onClick={() => setCurrentView('results')} />
              <SidebarItem icon={MapIcon} label="Interactive Map" active={currentView === 'map'} onClick={() => setCurrentView('map')} />
              
              <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 mt-6 px-3">Insights</div>
              <SidebarItem icon={Activity} label="Statistics" active={currentView === 'statistics'} onClick={() => setCurrentView('statistics')} />
              <SidebarItem icon={FileText} label="Reports" active={currentView === 'reports'} onClick={() => setCurrentView('reports')} />
              <SidebarItem icon={Bot} label="AI Assistant" active={currentView === 'ai'} onClick={() => setCurrentView('ai')} />

              <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 mt-6 px-3">System</div>
              <SidebarItem icon={History} label="History" active={currentView === 'history'} onClick={() => setCurrentView('history')} />
              <SidebarItem icon={Settings} label="Settings" active={currentView === 'settings'} onClick={() => setCurrentView('settings')} />
              <SidebarItem icon={ArrowLeftRight} label="Switch Workspace" active={false} onClick={() => setCurrentView('login')} />
            </div>
            <div className="p-4 border-t border-gray-800 text-white">
               <div className="flex items-center gap-3 px-2 py-2">
                 <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center text-primary font-bold text-sm">
                   MS
                 </div>
                 <div>
                   <div className="text-sm font-medium text-white">Mohamed Salah</div>
                   <div className="text-xs text-white">5G Planning Engineer</div>
                 </div>
               </div>
            </div>
          </>
        )}
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col min-w-0 bg-[#F4F6F8]">
        {/* Topbar */}
        <header className="h-16 bg-white border-b border-[var(--color-border)] flex items-center justify-between px-6 shrink-0 z-10 shadow-sm">
          <div className="flex-1 max-w-xl">
            <div className="relative">
              <Search className="w-4 h-4 absolute left-3 top-2.5 text-gray-400" />
              <input 
                type="text" 
                placeholder="Search cell ID, dataset, or report..." 
                className="w-full pl-10 pr-4 py-2 bg-gray-50 border border-gray-200 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-primary focus:bg-white transition-all"
              />
            </div>
          </div>
          <div className="flex items-center gap-4 ml-4">
            <button className="text-gray-400 hover:text-gray-600 relative">
              <Bell className="w-5 h-5" />
              <span className="absolute 1 top-0 right-0 w-2 h-2 bg-[var(--color-critical)] rounded-full border border-white"></span>
            </button>
            <button className="text-gray-400 hover:text-gray-600">
              <HelpCircle className="w-5 h-5" />
            </button>
          </div>
        </header>

        {/* View Content */}
        <div className="flex-1 overflow-auto p-6 relative">
          {isNetPulse ? renderNetPulseContent() : renderView()}
        </div>
      </main>
    </div>
  );
}
