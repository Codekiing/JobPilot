'use client';

import { ChangeEvent, useEffect, useMemo, useRef, useState } from 'react';
import companyLogoMap from './company-logo-map.json';
import companyTierMap from './company-tier-map.json';

type View = 'overview' | 'profile' | 'jobs' | 'pipeline' | 'resume' | 'autofill';
type Stage = 'matched' | 'shortlisted' | 'applied' | 'interview';
type LocalStatus = 'checking' | 'connected' | 'offline';
type ResumeState = 'ready' | 'parsing' | 'error';
type UiProfile = { name: string; status: string; target: string; city: string; skills: string; phone: string; email: string; gender: string; birthDate: string; currentCity: string; highestDegree: string; graduationDate: string; links: string; languages: string };
type StructuredProfile = {
  profile_id: string;
  metadata?: { updated_at?: string; source_resume_sha256?: string; [key: string]: unknown };
  identity: { name?: string | null; gender?: string | null; birth_date?: string | null; contact?: { email?: unknown; phone?: unknown; links?: unknown; [key: string]: unknown }; [key: string]: unknown };
  career: { career_stage?: string | null; current_city?: string | null; highest_degree?: string | null; graduation_date?: string | null; [key: string]: unknown };
  target: { primary_roles?: string[]; secondary_roles?: string[]; preferred_locations?: string[]; acceptable_locations?: string[]; work_modes?: string[]; salary?: { monthly_min_cny?: number | null; monthly_max_cny?: number | null; [key: string]: unknown }; [key: string]: unknown };
  capabilities: { skills?: { name: string; category?: string; proficiency?: string; evidence_refs?: string[]; [key: string]: unknown }[]; [key: string]: unknown };
  evidence?: {
    education?: EvidenceItem[];
    experience?: EvidenceItem[];
    projects?: EvidenceItem[];
    publications?: EvidenceItem[];
    quantified_achievements?: { claim: string; source_ref?: string }[];
    resume_sections?: EvidenceItem[];
    [key: string]: unknown;
  };
  preferences?: { culture_keywords?: string[]; [key: string]: unknown };
  constraints?: { deal_breakers?: string[]; [key: string]: unknown };
  completion?: { score?: number; match_ready?: boolean; missing_required?: MissingField[]; missing_recommended?: MissingField[]; [key: string]: unknown };
  matching_config: Record<string, unknown>;
  [key: string]: unknown;
};
type EvidenceItem = { id?: string; title?: string; date?: string | null; content?: string; source_ref?: string; [key: string]: unknown };
type MissingField = { field_path: string; label: string };
type ApiResume = { file_name: string; format: string; section_count: number; sections: { type: string; title: string; item_count: number; has_content: boolean }[]; warnings: string[]; project_count?: number };
type ResumeAnalysis = {
  fileName: string;
  format: string;
  sectionCount: number;
  projectCount: number;
  skillCount: number;
  sections: { type: string; title: string; itemCount: number; hasContent: boolean }[];
  warnings: string[];
  source: 'example' | 'local_components';
};
type Job = {
  id: number;
  company: string;
  initials: string;
  color: string;
  title: string;
  location: string;
  type: string;
  salary: string;
  tags: string[];
  score: number;
  reason: string;
  stage: Stage;
  saved: boolean;
  dismissed?: boolean;
  isNew?: boolean;
  description: string;
  applyUrl: string;
  platformApplyUrl: string;
  officialApplyUrl?: string;
  applySource: 'official' | 'nowcoder' | 'boss' | 'public';
  logoUrl?: string;
  sourceKind: 'official' | 'public_platform' | 'imported';
  companyTier: 'major' | 'mid_size' | 'unicorn' | 'growth' | 'small_business' | 'unknown';
  discoveredFrom: string;
};
type SearchCoverage = {
  plannedCompanies: number;
  reachableCompanies: number;
  companiesWithJobs: number;
  officialCandidates: number;
  platformCandidates: number;
  officialCompaniesWithJobs: number;
  platformSmallBusinessCandidates: number;
  byTier: Record<string, { plannedCompanies: number; companiesWithJobs: number }>;
  reachableByTier: Record<string, number>;
};
type ProviderReport = { source: string; status: string; jobCount: number };
type OfficialCompanyCoverage = { name: string; tier: string; careerUrl: string; status: 'matched' | 'reachable_no_match' | 'unreachable'; matchedJobCount: number };
type SearchReport = {
  mode: 'idle' | 'live' | 'error';
  coverage: SearchCoverage;
  providerCount: number;
  providers: ProviderReport[];
  officialCompanies: OfficialCompanyCoverage[];
  uniqueCompanies: number;
  largestCompanyCount: number;
  searchedAt?: string;
  message?: string;
};
type ApiMatchedJob = {
  source: string;
  source_job_id: string;
  title: string;
  company: string;
  locations?: string[];
  employment_type?: string;
  description?: string;
  requirements?: string;
  tags?: string[];
  salary_min?: number | null;
  salary_max?: number | null;
  salary_period?: string | null;
  application_url?: string;
  url?: string;
  source_kind?: string;
  company_tier?: Job['companyTier'];
  discovered_from?: string;
  application_source?: string;
  match: { total: number; reasons?: string[]; matched_skills?: string[] };
};

const DEFAULT_MATCH_LIMIT = 100;
const MAX_MATCH_LIMIT = 500;
const COMPANY_CATALOG_SIZE = 54;
const COMPANY_TIER_PLANS: Record<string, number> = { major: 18, mid_size: 16, unicorn: 12, growth: 8 };
const LOCAL_API_URL = process.env.NEXT_PUBLIC_JOBPILOT_API_URL || 'http://127.0.0.1:8765/jobpilot';

function normalizeCompanyKey(value: string): string {
  return value.toLowerCase().replace(/集团|科技|技术|有限责任公司|有限公司|股份|中国|huawei|pdd/g, '').replace(/[^a-z0-9\u4e00-\u9fff]/g, '');
}

const bundledLogoEntries = Object.entries(companyLogoMap as Record<string, string>).map(([company, url]) => ({ company, key: normalizeCompanyKey(company), url }));
const bundledTierEntries = Object.entries(companyTierMap as Record<string, { canonical: string; tier: Job['companyTier'] }>).map(([company, value]) => ({ key: normalizeCompanyKey(company), ...value }));

function resolveBundledLogo(company: string): string | undefined {
  const aliasKey = normalizeCompanyKey(company);
  const key = aliasKey === 'shopee' ? normalizeCompanyKey('深圳虾皮信息科技有限公司') : aliasKey;
  if (!key) return undefined;
  const exact = bundledLogoEntries.find((entry) => entry.key === key);
  if (exact) return exact.url;
  return bundledLogoEntries.find((entry) => entry.key.length >= 2 && (key.includes(entry.key) || entry.key.includes(key)))?.url;
}

function resolveCompanyTier(company: string): { canonical: string; tier: Job['companyTier'] } | undefined {
  const key = normalizeCompanyKey(company);
  if (!key) return undefined;
  const exact = bundledTierEntries.find((entry) => entry.key === key);
  if (exact) return { canonical: exact.canonical, tier: exact.tier };
  const related = bundledTierEntries.find((entry) => entry.key.length >= 2 && (key.includes(entry.key) || entry.key.includes(key)));
  return related ? { canonical: related.canonical, tier: related.tier } : undefined;
}

function isCompanyExcluded(company: string, excludedCompanies: string[]): boolean {
  const normalizedCompany = company.trim().toLowerCase();
  return excludedCompanies.some((value) => {
    const normalizedValue = value.trim().toLowerCase();
    return normalizedValue && (normalizedCompany.includes(normalizedValue) || normalizedValue.includes(normalizedCompany));
  });
}

const initialJobs: Job[] = [];
const emptyCoverage: SearchCoverage = { plannedCompanies: 0, reachableCompanies: 0, companiesWithJobs: 0, officialCandidates: 0, platformCandidates: 0, officialCompaniesWithJobs: 0, platformSmallBusinessCandidates: 0, byTier: {}, reachableByTier: {} };
const initialSearchReport: SearchReport = { mode: 'idle', coverage: emptyCoverage, providerCount: 0, providers: [], officialCompanies: [], uniqueCompanies: 0, largestCompanyCount: 0, message: '尚未搜索，因此不展示任何岗位。连接本地组件后点击搜索，页面只呈现本次实际获得的结果。' };

function stableJobId(value: string): number {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash) || 1;
}

function formatSalary(job: ApiMatchedJob): string {
  if (!job.salary_min && !job.salary_max) return '薪资面议';
  const unit = job.salary_period === 'day' ? '元/天' : 'K/月';
  const divisor = job.salary_period === 'day' ? 1 : 1000;
  const low = job.salary_min ? Math.round(job.salary_min / divisor) : null;
  const high = job.salary_max ? Math.round(job.salary_max / divisor) : null;
  return low && high ? `${low}-${high}${unit}` : `${low || high}${unit}`;
}

function apiJobToUi(job: ApiMatchedJob, index: number, existing?: Job): Job {
  const applicationUrl = job.application_url || job.url || '';
  const sourceKind: Job['sourceKind'] = job.source_kind === 'official' ? 'official' : job.source_kind === 'imported' ? 'imported' : 'public_platform';
  const applySource: Job['applySource'] = job.application_source === 'official' ? 'official' : applicationUrl.includes('zhipin.com') ? 'boss' : applicationUrl.includes('nowcoder.com') ? 'nowcoder' : 'public';
  const id = stableJobId(`${job.source}:${job.source_job_id}`);
  const tags = [...new Set([...(job.tags || []), ...(job.match.matched_skills || [])])].slice(0, 6);
  return {
    id,
    company: job.company || '公司待确认',
    initials: (job.company || '企').slice(0, 1),
    color: ['#1f6f54', '#315fa4', '#7b4bb3', '#b86825', '#3f5364'][index % 5],
    title: job.title,
    location: (job.locations || []).join('、') || '地点待确认',
    type: job.employment_type === 'internship' ? '实习' : job.employment_type === 'full_time' ? '社招' : '校招',
    salary: formatSalary(job),
    tags,
    score: Math.round(job.match.total),
    reason: job.match.reasons?.[0] || '已根据最新简历画像评分',
    stage: existing?.stage || 'matched',
    saved: existing?.saved || false,
    dismissed: existing?.dismissed,
    isNew: true,
    description: job.description || job.requirements || '岗位职责和任职要求请以投递页面为准。',
    applyUrl: applicationUrl,
    platformApplyUrl: applicationUrl,
    officialApplyUrl: sourceKind === 'official' ? applicationUrl : undefined,
    applySource,
    logoUrl: resolveBundledLogo(job.company || ''),
    sourceKind,
    companyTier: job.company_tier && job.company_tier !== 'unknown' ? job.company_tier : resolveCompanyTier(job.company || '')?.tier || 'unknown',
    discoveredFrom: job.discovered_from || job.source,
  };
}

function mergeBalancedJobs(candidates: Job[], limit: number): Job[] {
  const bestByRole = new Map<string, Job>();
  for (const job of candidates) {
    const key = `${normalizeCompanyKey(job.company)}|${job.title.toLowerCase().replace(/\s+/g, '')}`;
    const current = bestByRole.get(key);
    if (!current || (!current.officialApplyUrl && job.officialApplyUrl) || job.score > current.score) bestByRole.set(key, job);
  }
  const sorted = [...bestByRole.values()].sort((a, b) => b.score - a.score || Number(Boolean(b.officialApplyUrl)) - Number(Boolean(a.officialApplyUrl)));
  const jobsByCompany = new Map<string, Job[]>();
  for (const job of sorted) {
    const companyKey = normalizeCompanyKey(job.company) || `unknown-${job.id}`;
    const companyJobs = jobsByCompany.get(companyKey) || [];
    companyJobs.push(job);
    jobsByCompany.set(companyKey, companyJobs);
  }
  const selected: Job[] = [];
  let round = 0;
  while (selected.length < limit) {
    let added = false;
    for (const companyJobs of jobsByCompany.values()) {
      if (companyJobs[round]) {
        selected.push(companyJobs[round]);
        added = true;
        if (selected.length >= limit) break;
      }
    }
    if (!added) break;
    round += 1;
  }
  return selected;
}

const navItems: { id: View; label: string; icon: string }[] = [
  { id: 'overview', label: '概览', icon: '⌂' },
  { id: 'profile', label: '我的画像', icon: '◎' },
  { id: 'jobs', label: '岗位匹配', icon: '⌕' },
  { id: 'pipeline', label: '投递看板', icon: '◇' },
  { id: 'resume', label: '简历管理', icon: '▤' },
  { id: 'autofill', label: '自动填表', icon: '⌘' },
];

const viewTitles: Record<View, string> = {
  overview: '概览', profile: '我的画像', jobs: '岗位匹配', pipeline: '投递看板', resume: '简历管理', autofill: '自动填表',
};

const stageInfo: Record<Stage, { label: string; color: string }> = {
  matched: { label: '新匹配', color: '#708079' }, shortlisted: { label: '待确认', color: '#9a6a22' }, applied: { label: '已投递', color: '#2563a6' }, interview: { label: '面试中', color: '#176a48' },
};

const defaultProfile: UiProfile = { name: '示例候选人', status: '2027届硕士', target: '机器学习工程师', city: '北京', skills: 'Python、PyTorch、机器学习、深度学习', phone: '', email: '', gender: '', birthDate: '', currentCity: '', highestDegree: '硕士', graduationDate: '2027-06', links: '', languages: '' };
const defaultStructuredProfile: StructuredProfile = {
  schema_version: '1.0', profile_id: 'profile-example',
  identity: { name: '示例候选人', contact: {} },
  career: { career_stage: 'student', current_city: '北京', highest_degree: '硕士', graduation_date: '2027-06', experience_months: 6 },
  target: { employment_types: ['full_time'], primary_roles: ['机器学习工程师'], secondary_roles: [], preferred_locations: ['北京'], acceptable_locations: [], work_modes: [], salary: { monthly_min_cny: null, monthly_max_cny: null, negotiable: true } },
  capabilities: { skills: [{ name: 'Python' }, { name: 'PyTorch' }, { name: '机器学习' }, { name: '深度学习' }] },
  preferences: { culture_keywords: [] },
  constraints: { deal_breakers: [] },
  matching_config: { must_have_keywords: [], nice_to_have_keywords: [], excluded_keywords: [], weights: {} },
};
const defaultResumeAnalysis: ResumeAnalysis = {
  fileName: 'resume.example.md', format: 'md', sectionCount: 5, projectCount: 1, skillCount: 4, source: 'example', warnings: [],
  sections: [
    { type: 'basic_info', title: '基本信息', itemCount: 0, hasContent: true },
    { type: 'education', title: '教育背景', itemCount: 1, hasContent: true },
    { type: 'internship', title: '实习经历', itemCount: 1, hasContent: true },
    { type: 'project', title: '项目经历', itemCount: 1, hasContent: true },
    { type: 'skills', title: '核心技能', itemCount: 0, hasContent: true },
  ],
};

function formatUiProfile(value: StructuredProfile): UiProfile {
  const graduationYear = String(value.career.graduation_date || '').slice(0, 4);
  const degree = String(value.career.highest_degree || '');
  const stage = value.career.career_stage === 'experienced' ? '有工作经验' : graduationYear ? `${graduationYear}届${degree}` : degree;
  const contact = value.identity.contact || {};
  const languageValues = Array.isArray(value.capabilities.languages) ? value.capabilities.languages : [];
  return {
    name: String(value.identity.name || '候选人'),
    status: stage || '状态待补充',
    target: value.target.primary_roles?.[0] || '',
    city: value.target.preferred_locations?.[0] || String(value.career.current_city || ''),
    skills: (value.capabilities.skills || []).map((skill) => skill.name).filter(Boolean).join('、'),
    phone: String(contact.phone || ''),
    email: String(contact.email || ''),
    gender: String(value.identity.gender || ''),
    birthDate: String(value.identity.birth_date || ''),
    currentCity: String(value.career.current_city || ''),
    highestDegree: String(value.career.highest_degree || ''),
    graduationDate: String(value.career.graduation_date || ''),
    links: (Array.isArray(contact.links) ? contact.links : []).map(String).join('、'),
    languages: languageValues.map((item) => typeof item === 'string' ? item : String((item as { name?: string }).name || '')).filter(Boolean).join('、'),
  };
}

function mergeUiProfile(base: StructuredProfile, profile: UiProfile): StructuredProfile {
  const next = JSON.parse(JSON.stringify(base)) as StructuredProfile;
  next.identity = { ...next.identity, name: profile.name, gender: profile.gender || null, birth_date: profile.birthDate || null, contact: { ...(next.identity.contact || {}), phone: profile.phone || null, email: profile.email || null, links: profile.links.split(/[、,，|\n]/).map((item) => item.trim()).filter(Boolean) } };
  next.career = { ...next.career, current_city: profile.currentCity || null, highest_degree: profile.highestDegree || null, graduation_date: profile.graduationDate || null };
  next.target = { ...next.target, primary_roles: profile.target ? [profile.target] : [], preferred_locations: profile.city ? [profile.city] : [] };
  next.capabilities = { ...next.capabilities, skills: profile.skills.split(/[、,，|]/).map((name) => name.trim()).filter(Boolean).map((name) => ({ name })), languages: profile.languages.split(/[、,，|]/).map((name) => name.trim()).filter(Boolean) };
  return next;
}

function toBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += 0x8000) binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  return window.btoa(binary);
}

function loadStored<T>(key: string, fallback: T): T {
  if (typeof window === 'undefined') return fallback;
  try { return JSON.parse(window.localStorage.getItem(key) ?? '') as T; } catch { return fallback; }
}

function toResumeAnalysis(value: ApiResume, profile: StructuredProfile): ResumeAnalysis {
  return {
    fileName: value.file_name,
    format: value.format,
    sectionCount: value.section_count,
    projectCount: value.project_count ?? value.sections.filter((section) => ['project', 'research', 'open_source'].includes(section.type)).reduce((sum, section) => sum + Math.max(1, section.item_count), 0),
    skillCount: profile.capabilities.skills?.length || 0,
    sections: value.sections.map((section) => ({ type: section.type, title: section.title, itemCount: section.item_count, hasContent: section.has_content })),
    warnings: value.warnings || [],
    source: 'local_components',
  };
}

export default function Home() {
  const [view, setView] = useState<View>('overview');
  const [jobs, setJobs] = useState<Job[]>(initialJobs);
  const [matchLimit, setMatchLimit] = useState(DEFAULT_MATCH_LIMIT);
  const [profile, setProfile] = useState(defaultProfile);
  const [activeTab, setActiveTab] = useState('为你推荐');
  const [query, setQuery] = useState('');
  const [location, setLocation] = useState('全部城市');
  const [excludedCompanies, setExcludedCompanies] = useState<string[]>([]);
  const [matching, setMatching] = useState(false);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [notice, setNotice] = useState('');
  const [resumeName, setResumeName] = useState(defaultResumeAnalysis.fileName);
  const [resumeState, setResumeState] = useState<ResumeState>('ready');
  const [resumeAnalysis, setResumeAnalysis] = useState<ResumeAnalysis>(defaultResumeAnalysis);
  const [structuredProfile, setStructuredProfile] = useState<StructuredProfile>(defaultStructuredProfile);
  const [localStatus, setLocalStatus] = useState<LocalStatus>('checking');
  const [planReady, setPlanReady] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const [lastRankedProfileId, setLastRankedProfileId] = useState('');
  const [searchReport, setSearchReport] = useState<SearchReport>(initialSearchReport);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const storedJobs = loadStored<Job[]>('jobpilot.jobs.v2', initialJobs);
    const storedLimit = Math.max(DEFAULT_MATCH_LIMIT, Math.min(MAX_MATCH_LIMIT, loadStored('jobpilot.matchLimit', DEFAULT_MATCH_LIMIT)));
    setMatchLimit(storedLimit);
    setJobs(storedJobs.slice(0, storedLimit).map((job) => ({ ...job, logoUrl: resolveBundledLogo(job.company) || job.logoUrl })));
    setProfile({ ...defaultProfile, ...loadStored('jobpilot.profile.v2', defaultProfile) });
    setExcludedCompanies(loadStored<string[]>('jobpilot.excludedCompanies.v1', []));
    setResumeName(loadStored('jobpilot.resume.v2', defaultResumeAnalysis.fileName));
    setResumeAnalysis(loadStored('jobpilot.resumeAnalysis.v2', defaultResumeAnalysis));
    setStructuredProfile(loadStored('jobpilot.structuredProfile.v2', defaultStructuredProfile));
    setSearchReport(loadStored<SearchReport>('jobpilot.searchReport.v2', initialSearchReport));
    setHydrated(true);
  }, []);
  useEffect(() => { if (hydrated) window.localStorage.setItem('jobpilot.jobs.v2', JSON.stringify(jobs)); }, [jobs, hydrated]);
  useEffect(() => { if (hydrated) window.localStorage.setItem('jobpilot.matchLimit', JSON.stringify(matchLimit)); }, [matchLimit, hydrated]);
  useEffect(() => { if (hydrated) window.localStorage.setItem('jobpilot.profile.v2', JSON.stringify(profile)); }, [profile, hydrated]);
  useEffect(() => { if (hydrated) window.localStorage.setItem('jobpilot.excludedCompanies.v1', JSON.stringify(excludedCompanies)); }, [excludedCompanies, hydrated]);
  useEffect(() => { if (hydrated) window.localStorage.setItem('jobpilot.resume.v2', JSON.stringify(resumeName)); }, [resumeName, hydrated]);
  useEffect(() => { if (hydrated) window.localStorage.setItem('jobpilot.resumeAnalysis.v2', JSON.stringify(resumeAnalysis)); }, [resumeAnalysis, hydrated]);
  useEffect(() => { if (hydrated) window.localStorage.setItem('jobpilot.structuredProfile.v2', JSON.stringify(structuredProfile)); }, [structuredProfile, hydrated]);
  useEffect(() => { if (hydrated) window.localStorage.setItem('jobpilot.searchReport.v2', JSON.stringify(searchReport)); }, [searchReport, hydrated]);
  useEffect(() => {
    if (!hydrated) return;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 12000);
    fetch(`${LOCAL_API_URL}/health`, { signal: controller.signal })
      .then((response) => { if (!response.ok) throw new Error('offline'); return fetch(`${LOCAL_API_URL}/state`, { signal: controller.signal }); })
      .then(async (response) => {
        const payload = await response.json() as { data?: { resume?: ApiResume; profile?: StructuredProfile }; error?: { message?: string } };
        if (!response.ok || !payload.data?.resume || !payload.data.profile) throw new Error(payload.error?.message || '本地状态读取失败');
        const latestProfile = payload.data.profile;
        const latestResume = payload.data.resume;
        setStructuredProfile(latestProfile);
        setProfile(formatUiProfile(latestProfile));
        setResumeAnalysis(toResumeAnalysis(latestResume, latestProfile));
        setResumeName(latestResume.file_name);
        const storedLimit = Math.max(DEFAULT_MATCH_LIMIT, Math.min(MAX_MATCH_LIMIT, loadStored('jobpilot.matchLimit', DEFAULT_MATCH_LIMIT)));
        const storedJobs = loadStored<Job[]>('jobpilot.jobs.v2', initialJobs);
        const storedById = new Map(storedJobs.map((job) => [job.id, job]));
        const catalog = storedJobs.map((job) => {
          const stored = storedById.get(job.id);
          const withLogo = { ...job, logoUrl: resolveBundledLogo(job.company) || job.logoUrl };
          return stored ? { ...withLogo, stage: stored.stage, saved: stored.saved, dismissed: stored.dismissed } : withLogo;
        });
        if (catalog.length) {
          const ranked = await rankCatalog(latestProfile, catalog);
          setJobs(mergeBalancedJobs(ranked, storedLimit));
        }
        setLocalStatus('connected');
      })
      .catch(() => setLocalStatus('offline'))
      .finally(() => window.clearTimeout(timeout));
    return () => { controller.abort(); window.clearTimeout(timeout); };
  }, [hydrated]);

  const eligibleJobs = useMemo(() => jobs.filter((job) => !isCompanyExcluded(job.company, excludedCompanies)), [jobs, excludedCompanies]);
  const visibleJobs = useMemo(() => eligibleJobs.filter((job) => {
    if (job.dismissed) return false;
    if (activeTab === '高匹配' && job.score < 90) return false;
    if (activeTab === '最新发布' && !job.isNew) return false;
    if (location !== '全部城市' && !job.location.includes(location)) return false;
    const keyword = query.trim().toLowerCase();
    return !keyword || `${job.title}${job.company}${job.tags.join('')}`.toLowerCase().includes(keyword);
  }), [eligibleJobs, activeTab, location, query]);
  const profileCompletion = structuredProfile.completion?.score ?? Math.round(Object.values(profile).filter((value) => value.trim()).length / Object.keys(profile).length * 100);
  const shortlistCount = jobs.filter((job) => job.stage === 'shortlisted').length;
  const appliedCount = jobs.filter((job) => job.stage === 'applied' || job.stage === 'interview').length;

  function flash(message: string) {
    setNotice(message);
    window.setTimeout(() => setNotice(''), 2600);
  }
  function patchJob(id: number, patch: Partial<Job>) {
    setJobs((current) => current.map((job) => job.id === id ? { ...job, ...patch } : job));
    setSelectedJob((current) => current?.id === id ? { ...current, ...patch } : current);
  }
  function excludeCompany(value: string) {
    const company = value.trim();
    if (!company) return;
    setExcludedCompanies((current) => current.some((item) => item.toLowerCase() === company.toLowerCase()) ? current : [...current, company]);
    if (selectedJob && isCompanyExcluded(selectedJob.company, [company])) setSelectedJob(null);
    flash(`已排除公司：${company}`);
  }
  async function rankCatalog(nextProfile: StructuredProfile, catalog: Job[]): Promise<Job[]> {
    const response = await fetch(`${LOCAL_API_URL}/rank`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile: nextProfile, jobs: catalog.map((job) => ({ id: job.id, title: job.title, company: job.company, locations: [job.location], employment_type: 'campus', description: job.description, tags: job.tags, application_url: job.applyUrl })) }),
    });
    const payload = await response.json() as { data?: { jobs?: { id: string; match: { total: number; reasons: string[] } }[] }; error?: { message?: string } };
    if (!response.ok || !payload.data?.jobs) throw new Error(payload.error?.message || '本地 matcher 返回异常');
    const scores = new Map(payload.data.jobs.map((item) => [Number(item.id), item.match]));
    return catalog.map((job) => {
      const match = scores.get(job.id);
      return match ? { ...job, score: Math.round(match.total), reason: match.reasons[0] || '已由本地 matcher 根据简历画像重新评分' } : job;
    }).sort((a, b) => b.score - a.score || Number(Boolean(b.officialApplyUrl)) - Number(Boolean(a.officialApplyUrl)));
  }
  async function searchAndMatch(nextProfile: StructuredProfile): Promise<Job[]> {
    const response = await fetch(`${LOCAL_API_URL}/match`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        profile: nextProfile,
        online: true,
        official_first: true,
        company_tiers: ['major', 'mid_size', 'unicorn', 'growth'],
        sources: ['offershow', 'nowcoder', 'shixiseng', 'boss'],
        max_per_source: 100,
        limit: matchLimit,
        save: false,
      }),
    });
    const payload = await response.json() as {
      data?: {
        jobs?: ApiMatchedJob[];
        providers?: { source: string; status: string; job_count: number; metadata?: Record<string, unknown> }[];
        coverage?: { planned_companies?: number; companies_with_jobs?: number; official_candidates?: number; platform_candidates?: number; official_companies_with_jobs?: number; platform_small_business_candidates?: number; by_tier?: Record<string, { planned_companies?: number; companies_with_jobs?: number }> };
      };
      error?: { message?: string };
    };
    if (!response.ok || !payload.data?.jobs) throw new Error(payload.error?.message || '多渠道搜索返回异常');
    if (!payload.data.jobs.length) throw new Error('本次多渠道搜索没有获得可匹配岗位，请查看渠道覆盖报告');
    const existingById = new Map(jobs.map((job) => [job.id, job]));
    const mapped = payload.data.jobs.map((job, index) => {
      const id = stableJobId(`${job.source}:${job.source_job_id}`);
      return apiJobToUi(job, index, existingById.get(id));
    });
    const combined = mergeBalancedJobs(mapped, matchLimit);
    const officialDirectJobs = combined.filter((job) => Boolean(job.officialApplyUrl));
    const officialDirectCompanies = new Set(officialDirectJobs.map((job) => normalizeCompanyKey(job.company)).filter(Boolean));
    const realtimeOfficialCompanies = Number(payload.data.coverage?.official_companies_with_jobs || 0);
    const coverage = payload.data.coverage || {};
    const officialProvider = payload.data.providers?.find((provider) => provider.source === 'official_careers');
    const browserOfficialProvider = payload.data.providers?.find((provider) => provider.source === 'official_browser');
    const reachableCompanies = Number(officialProvider?.metadata?.reachable_companies || 0);
    const reachableByTier = (officialProvider?.metadata?.reachable_companies_by_tier || {}) as Record<string, number>;
    const browserCompanyCounts = (browserOfficialProvider?.metadata?.company_job_counts || {}) as Record<string, number>;
    const officialCompanies = ((officialProvider?.metadata?.coverage_entries || []) as { name?: unknown; tier?: unknown; career_url?: unknown; status?: unknown; matched_job_count?: unknown }[]).flatMap((entry) => {
      const status = entry.status;
      if (typeof entry.name !== 'string' || typeof entry.tier !== 'string' || typeof entry.career_url !== 'string' || (status !== 'matched' && status !== 'reachable_no_match' && status !== 'unreachable')) return [];
      const browserCount = Number(browserCompanyCounts[entry.name] || 0);
      return [{ name: entry.name, tier: entry.tier, careerUrl: entry.career_url, status: browserCount > 0 ? 'matched' : status, matchedJobCount: Number(entry.matched_job_count || 0) + browserCount } satisfies OfficialCompanyCoverage];
    });
    const matchedCompaniesByTier = new Map<string, Set<string>>();
    for (const job of combined) {
      const resolved = resolveCompanyTier(job.company);
      const tier = resolved?.tier || job.companyTier;
      if (!COMPANY_TIER_PLANS[tier]) continue;
      const companies = matchedCompaniesByTier.get(tier) || new Set<string>();
      companies.add(resolved?.canonical || normalizeCompanyKey(job.company));
      matchedCompaniesByTier.set(tier, companies);
    }
    const byTier = Object.fromEntries(Object.entries(COMPANY_TIER_PLANS).map(([tier, plannedCompanies]) => [tier, { plannedCompanies, companiesWithJobs: matchedCompaniesByTier.get(tier)?.size || 0 }]));
    const companyCounts = new Map<string, number>();
    for (const job of combined) {
      const key = normalizeCompanyKey(job.company) || job.company;
      companyCounts.set(key, (companyCounts.get(key) || 0) + 1);
    }
    const providers = (payload.data.providers || []).map((provider) => ({ source: provider.source, status: provider.status, jobCount: provider.job_count }));
    setSearchReport({
      mode: 'live',
      providerCount: providers.filter((provider) => !provider.source.startsWith('official_')).length,
      providers,
      officialCompanies,
      uniqueCompanies: companyCounts.size,
      largestCompanyCount: Math.max(0, ...companyCounts.values()),
      searchedAt: new Date().toISOString(),
      message: realtimeOfficialCompanies > 0
        ? `${reachableCompanies} 家官网入口本轮可访问；其中 ${realtimeOfficialCompanies} 家解析到与画像匹配的具体岗位。`
        : `${reachableCompanies} 家官网入口本轮可访问，但没有解析到与画像匹配的具体岗位；当前结果全部来自下方列明的补充渠道。`,
      coverage: {
        plannedCompanies: coverage.planned_companies || 0,
        reachableCompanies,
        companiesWithJobs: Math.max(coverage.companies_with_jobs || 0, officialDirectCompanies.size),
        officialCandidates: officialDirectJobs.length,
        platformCandidates: combined.length - officialDirectJobs.length,
        officialCompaniesWithJobs: officialDirectCompanies.size,
        platformSmallBusinessCandidates: coverage.platform_small_business_candidates || 0,
        byTier,
        reachableByTier,
      },
    });
    return combined;
  }
  async function runMatching() {
    setMatching(true);
    try {
      const ranked = await searchAndMatch(structuredProfile);
      setJobs(ranked);
      setLastRankedProfileId(structuredProfile.profile_id);
      setLocalStatus('connected');
      flash(`已完成官网优先搜索并匹配 ${ranked.length} 个岗位${excludedCompanies.length ? `，已排除 ${excludedCompanies.length} 个公司关键词` : ''}`);
    } catch (error) {
      setLocalStatus('offline');
      setSearchReport((current) => ({ ...current, mode: 'error', message: error instanceof Error ? error.message : '多渠道搜索失败' }));
      flash(error instanceof Error ? `无法调用本地组件：${error.message}` : '无法调用本地组件，请先启动 JobPilot API');
    } finally {
      setMatching(false);
    }
  }
  async function uploadResume(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    let apiReached = false;
    setResumeName(file.name);
    setResumeState('parsing');
    try {
      if (file.size > 8 * 1024 * 1024) throw new Error('简历文件不能超过 8MB');
      const response = await fetch(`${LOCAL_API_URL}/resume`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: file.name, content_base64: toBase64(await file.arrayBuffer()), save: false }),
      });
      apiReached = true;
      const payload = await response.json() as { data?: { resume?: ApiResume; profile?: StructuredProfile }; error?: { message?: string } };
      if (!response.ok || !payload.data?.resume || !payload.data.profile) throw new Error(payload.error?.message || '本地解析组件返回异常');
      const apiResume = payload.data.resume;
      const nextProfile = payload.data.profile;
      const nextAnalysis = toResumeAnalysis(apiResume, nextProfile);
      setProfile(formatUiProfile(nextProfile));
      setStructuredProfile(nextProfile);
      setResumeAnalysis(nextAnalysis);
      setResumeName(apiResume.file_name);
      setLocalStatus('connected');
      setResumeState('ready');
      setJobs([]);
      setLastRankedProfileId('');
      setSearchReport(initialSearchReport);
      flash(`已解析 ${file.name}；请补充并确认画像，保存后才会搜索岗位`);
      setView('profile');
    } catch (error) {
      setResumeState('error');
      setLocalStatus(apiReached ? 'connected' : 'offline');
      const message = error instanceof Error ? error.message : '本地简历解析失败';
      flash(message);
    } finally {
      event.target.value = '';
    }
  }
  async function saveProfileAndUpdate() {
    const next = mergeUiProfile(structuredProfile, profile);
    setMatching(true);
    try {
      const response = await fetch(`${LOCAL_API_URL}/profile`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile: next, save: true }),
      });
      const payload = await response.json() as { data?: StructuredProfile; error?: { message?: string } };
      if (!response.ok || !payload.data) throw new Error(payload.error?.message || '本地画像保存失败');
      const savedProfile = payload.data;
      setStructuredProfile(savedProfile);
      setProfile(formatUiProfile(savedProfile));
      try {
        setJobs(await searchAndMatch(savedProfile));
        setLastRankedProfileId(savedProfile.profile_id);
        setView('jobs');
      } catch (searchError) {
        setSearchReport((current) => ({ ...current, mode: 'error', message: searchError instanceof Error ? searchError.message : '多渠道搜索失败' }));
        throw new Error(`画像已保存，但岗位搜索未完成：${searchError instanceof Error ? searchError.message : '请重试'}`);
      }
      setLocalStatus('connected');
      flash('投递资料已写入本地画像，并同步更新岗位推荐');
    } catch (error) {
      setLocalStatus('offline');
      flash(error instanceof Error ? error.message : '本地 matcher 更新失败');
    } finally { setMatching(false); }
  }
  function resetDemo() {
    setJobs(initialJobs); setMatchLimit(DEFAULT_MATCH_LIMIT); setExcludedCompanies([]); setProfile(defaultProfile); setStructuredProfile(defaultStructuredProfile); setResumeName(defaultResumeAnalysis.fileName); setResumeAnalysis(defaultResumeAnalysis); setResumeState('ready'); setPlanReady(false); setSearchReport(initialSearchReport); flash('已恢复示例画像；岗位列表保持为空，等待真实搜索');
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">J</span><span>JobPilot</span></div>
        <nav className="nav" aria-label="主导航">
          <p className="nav-label">求职工作台</p>
          {navItems.slice(0, 4).map((item) => <button key={item.id} onClick={() => setView(item.id)} className={`nav-item ${view === item.id ? 'active' : ''}`}><span>{item.icon}</span>{item.label}{item.id === 'profile' && <b>{profileCompletion}%</b>}{item.id === 'jobs' && <b>{eligibleJobs.filter((job) => !job.dismissed).length}</b>}{item.id === 'pipeline' && <b>{shortlistCount + appliedCount}</b>}</button>)}
          <p className="nav-label second">工具</p>
          {navItems.slice(4).map((item) => <button key={item.id} onClick={() => setView(item.id)} className={`nav-item ${view === item.id ? 'active' : ''}`}><span>{item.icon}</span>{item.label}</button>)}
        </nav>
        <div className="privacy-card"><span className="shield">✓</span><div><strong>本地组件处理</strong><small>简历只发送到 127.0.0.1</small></div></div>
        <div className="profile-chip"><span className="avatar">{profile.name.slice(0, 1)}</span><div><strong>{profile.name}</strong><small>{profile.status}</small></div><button className="more-button" onClick={resetDemo} aria-label="重置演示数据">↺</button></div>
      </aside>

      <section className="workspace">
        <header className="topbar"><div className="breadcrumb"><span>工作台</span><i>/</i><strong>{viewTitles[view]}</strong></div><div className="top-actions"><span className={`service ${localStatus}`}><i />{localStatus === 'connected' ? '本地组件已连接' : localStatus === 'checking' ? '正在检查本地组件' : '本地组件未连接'}</span><button className="help-button" onClick={() => flash(localStatus === 'connected' ? '已连接 extractor、profile_builder 与 matcher' : '请在项目根目录运行：uv run --python 3.12 python -m jobpilot')}>? <span>使用说明</span></button></div></header>
        <div className="content">
          {view === 'overview' && <Overview profile={profile} jobs={eligibleJobs} matching={matching} profileCompletion={profileCompletion} shortlistCount={shortlistCount} appliedCount={appliedCount} onMatch={runMatching} onNavigate={setView} onSelect={setSelectedJob} onPatch={patchJob} />}
          {view === 'profile' && <ProfileView profile={profile} structuredProfile={structuredProfile} completion={profileCompletion} source={resumeAnalysis.source} localStatus={localStatus} onChange={setProfile} onSave={saveProfileAndUpdate} onResume={() => setView('resume')} />}
          {view === 'jobs' && <JobsView jobs={visibleJobs} allJobs={jobs} searchReport={searchReport} excludedCompanies={excludedCompanies} query={query} location={location} tab={activeTab} matchLimit={matchLimit} onMatchLimit={setMatchLimit} onQuery={setQuery} onLocation={setLocation} onExcludeCompany={excludeCompany} onRestoreCompany={(company) => setExcludedCompanies((current) => current.filter((item) => item !== company))} onClearExcluded={() => setExcludedCompanies([])} onTab={setActiveTab} onMatch={runMatching} matching={matching} profileSynced={Boolean(lastRankedProfileId && lastRankedProfileId === structuredProfile.profile_id)} onSelect={setSelectedJob} onPatch={patchJob} />}
          {view === 'pipeline' && <PipelineView jobs={jobs.filter((job) => !job.dismissed)} onSelect={setSelectedJob} onPatch={patchJob} />}
          {view === 'resume' && <ResumeView name={resumeName} state={resumeState} analysis={resumeAnalysis} localStatus={localStatus} inputRef={fileInput} onUpload={uploadResume} />}
          {view === 'autofill' && <AutofillView jobs={jobs.filter((job) => job.stage === 'shortlisted' || job.stage === 'applied')} ready={planReady} onGenerate={() => { setPlanReady(true); flash('已生成本地填表计划'); }} onApply={(id) => { patchJob(id, { stage: 'applied' }); flash('已标记为已投递'); }} />}
        </div>
      </section>

      <nav className="mobile-nav" aria-label="移动端导航">
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => setView(item.id)}
            className={view === item.id ? 'active' : ''}
            aria-current={view === item.id ? 'page' : undefined}
          >
            <span>{item.icon}</span>
            {item.label.replace('我的', '').replace('岗位', '').replace('管理', '')}
          </button>
        ))}
      </nav>

      {selectedJob && <JobDrawer job={selectedJob} onClose={() => setSelectedJob(null)} onPatch={(patch) => patchJob(selectedJob.id, patch)} onNotice={flash} />}
      {notice && <div className="toast" role="status"><span>✓</span>{notice}</div>}
    </main>
  );
}

function PageIntro({ eyebrow, title, text, action }: { eyebrow: string; title: string; text: string; action?: React.ReactNode }) {
  return <section className="page-intro"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{text}</p></div>{action}</section>;
}

function Overview({ profile, jobs, matching, profileCompletion, shortlistCount, appliedCount, onMatch, onNavigate, onSelect, onPatch }: { profile: typeof defaultProfile; jobs: Job[]; matching: boolean; profileCompletion: number; shortlistCount: number; appliedCount: number; onMatch: () => void; onNavigate: (view: View) => void; onSelect: (job: Job) => void; onPatch: (id: number, patch: Partial<Job>) => void }) {
  const topJobs = jobs.filter((job) => !job.dismissed).sort((a, b) => b.score - a.score).slice(0, 3);
  return <>
    <PageIntro eyebrow="TODAY · JOB SEARCH PLAN" title={`下午好，${profile.name.slice(0, 1)}同学 👋`} text={`当前目标：${profile.target} · ${profile.city}`} action={<button className={`primary-button ${matching ? 'loading' : ''}`} onClick={onMatch} disabled={matching}><span>{matching ? '↻' : '✦'}</span>{matching ? '正在匹配…' : '重新匹配岗位'}</button>} />
    <section className="stats-grid" aria-label="求职数据概览">
      <button className="stat-card" onClick={() => onNavigate('profile')}><div className="stat-head"><span className="stat-icon violet">◉</span><em>去完善</em></div><strong>{profileCompletion}<small>%</small></strong><p>画像完整度</p><div className="mini-progress"><i style={{ width: `${profileCompletion}%` }} /></div></button>
      <button className="stat-card" onClick={() => onNavigate('jobs')}><div className="stat-head"><span className="stat-icon blue">⌕</span><em>查看</em></div><strong>{jobs.filter((job) => !job.dismissed).length}</strong><p>匹配岗位</p><small>{jobs.filter((job) => job.score >= 90 && !job.dismissed).length} 个高度匹配</small></button>
      <button className="stat-card" onClick={() => onNavigate('pipeline')}><div className="stat-head"><span className="stat-icon amber">◇</span><em>处理</em></div><strong>{shortlistCount}</strong><p>待确认岗位</p><small>点击进入投递看板</small></button>
      <button className="stat-card" onClick={() => onNavigate('pipeline')}><div className="stat-head"><span className="stat-icon green">↗</span><em>进展</em></div><strong>{appliedCount}</strong><p>投递进程</p><small>{jobs.filter((job) => job.stage === 'interview').length} 个进入面试流程</small></button>
    </section>
    <section className="main-grid">
      <div className="job-panel panel"><div className="panel-head"><div><h2>优先处理的岗位</h2><p>点击岗位可查看匹配依据并推进投递</p></div><button className="text-button" onClick={() => onNavigate('jobs')}>查看全部 <span>→</span></button></div><div className="job-list">{topJobs.map((job) => <JobRow key={job.id} job={job} onSelect={onSelect} onPatch={onPatch} />)}</div></div>
      <aside className="right-column"><section className="panel journey-panel"><div className="panel-head compact"><div><h2>今天优先做</h2><p>完成后数据会实时更新</p></div></div><div className="task-list"><button onClick={() => onNavigate('profile')}><span>1</span><div><strong>从简历生成画像</strong><small>使用本地 profile_builder</small></div><b>→</b></button><button onClick={() => onNavigate('jobs')}><span>2</span><div><strong>确认高匹配岗位</strong><small>{shortlistCount} 个岗位等待处理</small></div><b>→</b></button><button onClick={() => onNavigate('autofill')}><span>3</span><div><strong>生成填表计划</strong><small>投递前仍需人工确认</small></div><b>→</b></button></div></section><section className="focus-card"><span className="spark">✦</span><p>真实组件链</p><h3>简历经 extractor 拆解，再由 profile_builder 生成画像并交给 matcher。</h3><button onClick={() => onNavigate('resume')}>查看简历与画像来源 <span>→</span></button></section></aside>
    </section>
  </>;
}

function CompanyLogo({ job }: { job: Job }) {
  const [failedUrl, setFailedUrl] = useState<string>();
  const showImage = Boolean(job.logoUrl) && failedUrl !== job.logoUrl;
  return <span className={`company-logo ${showImage ? 'has-image' : 'is-fallback'}`} style={{ background: showImage ? '#fff' : job.color }}>{showImage ? <img src={job.logoUrl} alt={`${job.company} Logo`} decoding="async" onError={() => setFailedUrl(job.logoUrl)} /> : job.initials}</span>;
}

function JobRow({ job, onSelect, onPatch }: { job: Job; onSelect: (job: Job) => void; onPatch: (id: number, patch: Partial<Job>) => void }) {
  const sourceLabel = job.applySource === 'official' ? '官网' : job.applySource === 'boss' ? 'BOSS' : job.applySource === 'nowcoder' ? '牛客' : '公开平台';
  const directLinkLabel = job.applySource === 'official' ? '官网投递' : `${sourceLabel}查看`;
  const discoveryLabel = job.sourceKind === 'official' ? '官网发现' : job.discoveredFrom === 'nowcoder' ? '牛客发现' : job.discoveredFrom === 'offershow' ? 'OfferShow 发现' : '平台发现';
  return <article className="job-row" onClick={() => onSelect(job)}><CompanyLogo job={job} /><div className="job-main"><div className="job-title-line"><h3>{job.title}</h3><span className={`link-source ${job.applySource === 'official' ? 'official' : ''}`}>{sourceLabel}投递</span><span className={`discovery-source ${job.sourceKind === 'official' ? 'official' : ''}`}>{discoveryLabel}</span><span className="match-score">{job.score}% 匹配</span></div><p className="job-meta"><strong>{job.company}</strong><i />{job.location} · {job.type}<i />{job.salary}</p><div className="tag-line">{job.tags.map((tag) => <span key={tag}>{tag}</span>)}</div></div><div className="job-aside"><div className="card-actions"><button aria-label={job.saved ? '取消收藏' : '收藏岗位'} onClick={(event) => { event.stopPropagation(); onPatch(job.id, { saved: !job.saved, stage: job.saved ? 'matched' : 'shortlisted' }); }} className={`save-button ${job.saved ? 'saved' : ''}`}>{job.saved ? '◆' : '◇'}</button><a className={`card-apply ${job.applySource === 'official' ? 'official' : ''}`} href={job.applyUrl} target="_blank" rel="noopener noreferrer" aria-label={`${directLinkLabel}：${job.company} ${job.title}`} onClick={(event) => event.stopPropagation()}>{directLinkLabel} <span>↗</span></a></div><small>{job.reason}</small></div></article>;
}

function ProfileView({ profile, structuredProfile, completion, source, localStatus, onChange, onSave, onResume }: { profile: UiProfile; structuredProfile: StructuredProfile; completion: number; source: ResumeAnalysis['source']; localStatus: LocalStatus; onChange: (profile: UiProfile) => void; onSave: () => void; onResume: () => void }) {
  const applicationFields: { key: keyof UiProfile; label: string; placeholder: string; type?: string; wide?: boolean }[] = [
    { key: 'name', label: '姓名', placeholder: '你的姓名' },
    { key: 'phone', label: '手机号', placeholder: '用于接收招聘流程通知' },
    { key: 'email', label: '邮箱', placeholder: '常用招聘联系邮箱' },
    { key: 'gender', label: '性别', placeholder: '按投递表单要求填写' },
    { key: 'birthDate', label: '出生日期', placeholder: '出生日期', type: 'date' },
    { key: 'currentCity', label: '现居城市', placeholder: '例如：深圳' },
    { key: 'highestDegree', label: '最高学历', placeholder: '例如：硕士' },
    { key: 'graduationDate', label: '毕业时间', placeholder: '毕业年月', type: 'month' },
    { key: 'links', label: '个人链接', placeholder: 'GitHub、个人主页或作品集链接，用顿号或换行分隔', wide: true },
    { key: 'languages', label: '语言能力', placeholder: '例如：英语 CET-6、普通话', wide: true },
    { key: 'skills', label: '专业技能', placeholder: '用顿号分隔技能', wide: true },
  ];
  const matchingFields: { key: keyof UiProfile; label: string; placeholder: string }[] = [
    { key: 'target', label: '目标岗位', placeholder: '例如：大模型算法工程师' },
    { key: 'city', label: '期望城市', placeholder: '例如：深圳' },
  ];
  const missingFieldMap: Record<string, keyof UiProfile> = {
    'identity.name': 'name', 'identity.contact.phone': 'phone', 'identity.contact.email': 'email',
    'identity.gender': 'gender', 'identity.birth_date': 'birthDate', 'career.current_city': 'currentCity',
    'career.highest_degree': 'highestDegree', 'career.graduation_date': 'graduationDate',
    'capabilities.skills': 'skills', 'capabilities.languages': 'languages', 'identity.contact.links': 'links',
  };
  const sourceLabel = source === 'local_components' ? '由当前简历生成' : '由项目示例简历生成';
  const evidence = structuredProfile.evidence || {};
  const profileScore = structuredProfile.completion?.score ?? completion;
  const evidenceGroups: { key: string; title: string; items: EvidenceItem[] }[] = [
    { key: 'education', title: '教育经历', items: evidence.education || [] },
    { key: 'experience', title: '实习 / 工作经历', items: evidence.experience || [] },
    { key: 'projects', title: '项目与开源', items: evidence.projects || [] },
    { key: 'publications', title: '论文与成果', items: evidence.publications || [] },
  ];
  const missing = [...(structuredProfile.completion?.missing_required || []), ...(structuredProfile.completion?.missing_recommended || [])];
  const renderField = (field: { key: keyof UiProfile; label: string; placeholder: string; type?: string; wide?: boolean }, optional = false) => <label key={field.key} className={field.wide ? 'wide' : ''}><span>{field.label}{optional && <em>仅用于匹配</em>}</span>{field.wide ? <textarea id={`profile-field-${field.key}`} value={profile[field.key]} placeholder={field.placeholder} onChange={(event) => onChange({ ...profile, [field.key]: event.target.value })} /> : <input id={`profile-field-${field.key}`} type={field.type || 'text'} value={profile[field.key]} placeholder={field.placeholder} onChange={(event) => onChange({ ...profile, [field.key]: event.target.value })} />}</label>;
  const focusMissingField = (fieldPath: string) => {
    const key = missingFieldMap[fieldPath];
    if (!key) { onResume(); return; }
    const element = document.getElementById(`profile-field-${key}`);
    element?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    window.setTimeout(() => element?.focus(), 350);
  };
  return <>
    <PageIntro eyebrow="PROFILE · APPLICATION DATA" title="可直接填入招聘网站的候选人资料" text="画像字段对应常见网申表单；简历已识别的教育、经历和项目会直接复用，只补真正缺失的投递资料。" action={<div className="completion-ring" style={{ background: `conic-gradient(var(--green) 0 ${profileScore}%, #e5eae7 ${profileScore}%)` }}><strong>{profileScore}%</strong><span>投递完整度</span></div>} />
    <section className="component-chain" aria-label="本地组件链"><span className="done">1 · extractor 拆解</span><i>→</i><span className="done">2 · 补全并确认画像</span><i>→</i><span className={localStatus === 'connected' ? 'done' : ''}>3 · matcher 动态搜索</span></section>
    <section className="profile-layout">
      <div className="profile-primary">
        <div className="panel form-panel">
          <div className="panel-head"><div><h2>一键投递资料</h2><p>{sourceLabel} · 与招聘网站常见字段保持一致</p></div><span className={`component-badge ${source}`}>{source === 'local_components' ? '本地最新画像' : '示例数据'}</span></div>
          <div className="profile-form">{applicationFields.map((field) => renderField(field))}<div className="form-section-title"><strong>岗位匹配信息</strong><span>只影响岗位推荐，不会作为网申必填项</span></div>{matchingFields.map((field) => renderField(field, true))}</div>
          <div className="form-actions"><span>确认后写入本地画像，并立即按这份画像动态搜索岗位</span><button className="primary-button" onClick={onSave}>确认保存并搜索岗位</button></div>
        </div>
        <section className="panel evidence-panel"><div className="panel-head"><div><h2>可填入网申的经历资料</h2><p>{evidenceGroups.reduce((sum, group) => sum + group.items.length, 0)} 条结构化经历 · {(evidence.quantified_achievements || []).length} 条量化成果</p></div><span className="component-badge local_components">可追溯到原简历</span></div><div className="evidence-groups">{evidenceGroups.map((group) => <section key={group.key}><header><h3>{group.title}</h3><span>{group.items.length}</span></header>{group.items.length ? group.items.map((item, index) => <details key={item.id || `${group.key}-${index}`}><summary><span>{item.title || '未命名条目'}</span><small>{item.date || '简历已识别'}</small></summary><p>{item.content}</p></details>) : <p className="evidence-empty">简历中未识别到此类内容</p>}</section>)}</div>{Boolean(evidence.quantified_achievements?.length) && <div className="achievement-list"><h3>量化成果</h3>{evidence.quantified_achievements?.map((item, index) => <p key={`${item.source_ref}-${index}`}><span>{index + 1}</span>{item.claim}</p>)}</div>}</section>
      </div>
      <aside className="profile-side">
        <section className="panel insight-card"><p>投递摘要 · {sourceLabel}</p><h3>{profile.name || '姓名待补充'}</h3><div><span>{profile.highestDegree || '学历待识别'}</span><span>{structuredProfile.career.experience_months ? `${structuredProfile.career.experience_months} 个月经历` : '经历待识别'}</span><span>{profile.graduationDate || '毕业时间待补充'}</span></div></section>
        <section className="panel skill-card"><h3>技能画像 <span>{structuredProfile.capabilities.skills?.length || 0}</span></h3><div>{(structuredProfile.capabilities.skills || []).map((skill) => <span key={skill.name} className={skill.proficiency === 'advanced' ? 'advanced' : ''} title={`${skill.category || '技能'} · ${skill.proficiency || '未分级'}`}>{skill.name}<small>{skill.proficiency === 'advanced' ? '进阶' : skill.proficiency === 'intermediate' ? '熟练' : ''}</small></span>)}</div></section>
        <section className="panel score-list"><h3>投递资料待补充 <span>{missing.length}</span></h3>{missing.length ? missing.map((item) => <button type="button" key={item.field_path} onClick={() => focusMissingField(item.field_path)}><i />{item.label}<b>{missingFieldMap[item.field_path] ? '去补充 →' : '更新简历 →'}</b></button>) : <p><i className="done" />常见网申资料已完整</p>}</section>
      </aside>
    </section>
  </>;
}

function SearchCoveragePanel({ report, matching }: { report: SearchReport; matching: boolean }) {
  const tierLabels: Record<string, string> = { major: '大厂', mid_size: '中型公司', unicorn: '独角兽', growth: '成长型公司' };
  const providerLabels: Record<string, string> = { official_careers: '官网静态/API', official_browser: '官网动态页面', nowcoder_company_search: '牛客·逐家大厂检索', boss: 'BOSS', shixiseng: '实习僧', nowcoder: '牛客', offershow: 'OfferShow' };
  const planned = report.coverage.plannedCompanies || COMPANY_CATALOG_SIZE;
  const gaps = report.officialCompanies.filter((company) => company.status !== 'matched');
  return <section className={`search-coverage ${report.mode}`} aria-live="polite"><header><div><span className={matching ? 'search-spinner' : ''}>{matching ? '↻' : report.mode === 'live' ? '✓' : report.mode === 'error' ? '!' : '⌕'}</span><div><strong>{matching ? '正在检查企业官网，并行补充公开招聘平台' : report.mode === 'live' ? '本次搜索来源已核算' : report.mode === 'error' ? '本次多渠道搜索未完成' : '尚未执行岗位搜索'}</strong><small>{matching ? `尝试 ${COMPANY_CATALOG_SIZE} 家企业官网，并分别记录成功、空结果与失败` : report.message || '点击右上角开始真实搜索'}</small></div></div><em>{report.mode === 'live' ? '本次实时结果' : '无岗位数据'}</em></header><div className="search-phases"><div><b>1</b><span><strong>官网岗位解析</strong><small>尝试 {planned} 家 · 可访问 {report.coverage.reachableCompanies ?? 0} 家 · 真正解析到岗位 {report.coverage.officialCompaniesWithJobs} 家</small></span></div><i>→</i><div><b>2</b><span><strong>公开平台补充</strong><small>{report.providerCount} 个渠道 · 每个渠道单独列明数量</small></span></div><i>→</i><div><b>3</b><span><strong>跨公司均衡排序</strong><small>{report.uniqueCompanies} 家公司 · 单家公司最多 {report.largestCompanyCount} 条</small></span></div></div>{report.providers.length > 0 && <div className="provider-breakdown" aria-label="岗位来源明细">{report.providers.map((provider) => <span key={provider.source} className={provider.source.startsWith('official_') ? 'official' : ''}><strong>{providerLabels[provider.source] || provider.source}</strong><b>{provider.jobCount} 条</b><small>{provider.status}</small></span>)}</div>}{Object.keys(report.coverage.byTier).length > 0 && <><div className="tier-coverage">{Object.entries(report.coverage.byTier).map(([tier, value]) => <span key={tier}>{tierLabels[tier] || tier}<small>官网可访问 {report.coverage.reachableByTier?.[tier] ?? '—'}/{value.plannedCompanies}</small><b>解析匹配 {value.companiesWithJobs} 家</b></span>)}</div><p className="coverage-legend">“可访问”不等于“已获得岗位”。只有拿到具体岗位详情和投递链接，才会标为官网来源；其余结果按实际平台标注。</p></>}{gaps.length > 0 && <details className="coverage-gaps"><summary>查看 {gaps.length} 家未解析出匹配岗位的官网（不代表没有在招）</summary><div>{gaps.map((company) => <a key={company.name} href={company.careerUrl} target="_blank" rel="noopener noreferrer"><strong>{company.name}</strong><small>{tierLabels[company.tier] || company.tier} · {company.status === 'unreachable' ? '本轮访问失败' : '可访问但未解析到匹配岗位'}</small><span>官网 ↗</span></a>)}</div></details>}</section>;
}

function JobsView({ jobs, allJobs, searchReport, excludedCompanies, query, location, tab, matchLimit, onMatchLimit, onQuery, onLocation, onExcludeCompany, onRestoreCompany, onClearExcluded, onTab, onMatch, matching, profileSynced, onSelect, onPatch }: { jobs: Job[]; allJobs: Job[]; searchReport: SearchReport; excludedCompanies: string[]; query: string; location: string; tab: string; matchLimit: number; onMatchLimit: (value: number) => void; onQuery: (value: string) => void; onLocation: (value: string) => void; onExcludeCompany: (value: string) => void; onRestoreCompany: (value: string) => void; onClearExcluded: () => void; onTab: (value: string) => void; onMatch: () => void; matching: boolean; profileSynced: boolean; onSelect: (job: Job) => void; onPatch: (id: number, patch: Partial<Job>) => void }) {
  const [companyInput, setCompanyInput] = useState('');
  const [matchLimitInput, setMatchLimitInput] = useState(String(matchLimit));
  const companyOptions = useMemo(() => [...new Set(allJobs.map((job) => job.company))].sort((a, b) => a.localeCompare(b, 'zh-CN')), [allJobs]);
  const addCompany = () => {
    if (!companyInput.trim()) return;
    onExcludeCompany(companyInput);
    setCompanyInput('');
  };
  const commitMatchLimit = () => {
    const parsed = Number(matchLimitInput);
    const next = Number.isFinite(parsed) ? Math.max(DEFAULT_MATCH_LIMIT, Math.min(MAX_MATCH_LIMIT, Math.round(parsed))) : DEFAULT_MATCH_LIMIT;
    setMatchLimitInput(String(next));
    onMatchLimit(next);
  };
  return <><PageIntro eyebrow="DISCOVER → MATCH" title="只展示实际搜到、来源可追溯的岗位" text="系统会尝试 54 家企业官网并补充 4 个公开平台；只有解析出具体岗位与投递链接时才计入该来源，不把“访问过官网”说成“官网岗位”。" action={<div className="match-action"><label className="match-limit"><span>匹配数量</span><input type="number" min={DEFAULT_MATCH_LIMIT} max={MAX_MATCH_LIMIT} step={1} value={matchLimitInput} onChange={(event) => setMatchLimitInput(event.target.value)} onBlur={commitMatchLimit} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); commitMatchLimit(); event.currentTarget.blur(); } }} aria-label="匹配岗位数量" /><small>100–500，可手动输入</small></label><button className={`primary-button ${matching ? 'loading' : ''}`} onClick={onMatch} disabled={matching}><span>{matching ? '↻' : '✦'}</span>{matching ? '正在搜索…' : `搜索并匹配 ${matchLimit} 个`}</button></div>} /><SearchCoveragePanel report={searchReport} matching={matching} />{profileSynced && <div className="ranking-status"><span>✓</span><div><strong>已按本地最新简历动态重排，并优先覆盖更多公司</strong><small>先选取每家公司的最高匹配岗位，再进入下一轮，避免少数公司占满列表</small></div></div>}<section className="panel jobs-browser"><div className="filter-bar"><label className="search-box"><span>⌕</span><input value={query} onChange={(e) => onQuery(e.target.value)} placeholder="搜索岗位、公司或技能" /></label><select value={location} onChange={(e) => onLocation(e.target.value)} aria-label="选择城市"><option>全部城市</option><option>深圳</option><option>上海</option><option>北京</option><option>杭州</option><option>广州</option><option>东莞</option></select><div className="company-exclude"><input list="jobpilot-company-options" value={companyInput} onChange={(event) => setCompanyInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); addCompany(); } }} placeholder="排除公司或关键词" aria-label="排除公司" /><button type="button" onClick={addCompany} disabled={!companyInput.trim()}>排除</button><datalist id="jobpilot-company-options">{companyOptions.map((company) => <option key={company} value={company} />)}</datalist></div></div>{excludedCompanies.length > 0 && <div className="excluded-companies"><span>已排除</span>{excludedCompanies.map((company) => <button key={company} onClick={() => onRestoreCompany(company)} title={`恢复 ${company}`}>{company} <b>×</b></button>)}<button className="clear-excluded" onClick={onClearExcluded}>全部恢复</button><small>刷新或重新匹配后仍然生效</small></div>}<div className="tabs large-tabs">{['为你推荐', '高匹配', '最新发布'].map((item) => <button key={item} onClick={() => onTab(item)} className={tab === item ? 'active' : ''}>{item}</button>)}<span className="results-count">当前显示 {jobs.length} 个岗位{excludedCompanies.length ? ` · 已排除 ${excludedCompanies.length} 项` : ''}</span></div>{jobs.length ? <div className="job-list">{jobs.map((job) => <JobRow key={job.id} job={job} onSelect={onSelect} onPatch={onPatch} />)}</div> : <div className="empty-state"><span>⌕</span><h3>{searchReport.mode === 'idle' ? '尚未进行真实岗位搜索' : '没有符合当前条件的岗位'}</h3><p>{searchReport.mode === 'idle' ? '页面不会用演示缓存冒充推荐。请先启动本地 JobPilot API，再点击“搜索并匹配”。' : '试试恢复被排除的公司，或清空关键词与城市筛选。'}</p>{searchReport.mode === 'idle' ? <button onClick={onMatch}>开始真实搜索</button> : <button onClick={() => { onQuery(''); onLocation('全部城市'); onTab('为你推荐'); onClearExcluded(); }}>清除全部筛选</button>}</div>}</section></>;
}

function PipelineView({ jobs, onSelect, onPatch }: { jobs: Job[]; onSelect: (job: Job) => void; onPatch: (id: number, patch: Partial<Job>) => void }) {
  const stages: Stage[] = ['matched', 'shortlisted', 'applied', 'interview'];
  return <><PageIntro eyebrow="APPLICATION PIPELINE" title="每个机会都清楚下一步" text="通过卡片上的按钮推进状态，所有统计会同步更新。" /><section className="kanban">{stages.map((stage, stageIndex) => <div className="kanban-column" key={stage}><header><span style={{ background: stageInfo[stage].color }} />{stageInfo[stage].label}<b>{jobs.filter((job) => job.stage === stage).length}</b></header><div className="kanban-list">{jobs.filter((job) => job.stage === stage).map((job) => <article className="kanban-card" key={job.id} onClick={() => onSelect(job)}><div className="kanban-company"><CompanyLogo job={job} /><strong>{job.company}</strong><em>{job.score}%</em></div><h3>{job.title}</h3><p>{job.location} · {job.type}</p><div className="kanban-actions">{stageIndex > 0 && <button onClick={(e) => { e.stopPropagation(); onPatch(job.id, { stage: stages[stageIndex - 1] }); }}>←</button>}{stageIndex < stages.length - 1 && <button onClick={(e) => { e.stopPropagation(); onPatch(job.id, { stage: stages[stageIndex + 1], saved: true }); }}>推进 <span>→</span></button>}</div></article>)}{!jobs.some((job) => job.stage === stage) && <div className="kanban-empty">暂无岗位</div>}</div></div>)}</section></>;
}

function ResumeView({ name, state, analysis, localStatus, inputRef, onUpload }: { name: string; state: ResumeState; analysis: ResumeAnalysis; localStatus: LocalStatus; inputRef: React.RefObject<HTMLInputElement | null>; onUpload: (event: ChangeEvent<HTMLInputElement>) => void }) {
  const stateLabel = state === 'parsing' ? '组件处理中…' : state === 'error' ? '解析失败' : analysis.source === 'local_components' ? '本地解析完成' : '示例结果';
  return <><PageIntro eyebrow="RESUME · EXTRACTOR" title="简历是画像的真实数据源" text="文件只发送到本机 127.0.0.1，由项目中的 extractor 和 profile_builder 处理。" /><section className="component-chain" aria-label="本地组件链"><span className={analysis.source === 'local_components' ? 'done' : ''}>1 · extractor</span><i>→</i><span className={analysis.source === 'local_components' ? 'done' : ''}>2 · profile_builder</span><i>→</i><span className={analysis.source === 'local_components' && localStatus === 'connected' ? 'done' : ''}>3 · matcher</span></section>{localStatus === 'offline' && <section className="local-api-banner" role="status"><span>!</span><div><strong>本地组件尚未连接</strong><p>在 JobPilot 项目根目录运行 <code>uv run --python 3.12 python -m jobpilot</code>，然后重新选择简历。</p></div></section>}<section className="resume-grid"><div className="panel resume-card"><div className="resume-file"><span>{analysis.format.toUpperCase()}</span><div><h3>{name}</h3><p>{analysis.source === 'local_components' ? '来自本次本地解析' : '与当前画像对应的项目示例'}</p></div><b className={state === 'error' ? 'error' : ''}>{stateLabel}</b></div><div className="resume-sections"><div><strong>{analysis.sectionCount}</strong><span>识别栏目</span></div><div><strong>{analysis.projectCount}</strong><span>项目 / 研究</span></div><div><strong>{analysis.skillCount}</strong><span>技能标签</span></div></div><button className="secondary-button" disabled={state === 'parsing'} onClick={() => inputRef.current?.click()}>{state === 'parsing' ? 'extractor 正在解析…' : '选择新的简历文件'}</button><input ref={inputRef} className="sr-only" type="file" accept=".pdf,.doc,.docx,.odt,.tex,.latex,.md,.markdown,.txt" onChange={onUpload} /></div><div className="panel extracted-card"><div className="panel-head"><div><h2>真实解析结果</h2><p>{analysis.source === 'local_components' ? '以下栏目来自本次上传文件' : '以下栏目来自 profile_builder/examples/resume.example.json'}</p></div><span className={`component-badge ${analysis.source}`}>{analysis.source === 'local_components' ? 'extractor 输出' : '项目示例'}</span></div>{analysis.sections.map((section, index) => <div className="extracted-row" key={`${section.type}-${index}`}><span>{section.hasContent ? '✓' : index + 1}</span><div><strong>{section.title}</strong><small>{section.hasContent ? `已识别${section.itemCount ? ` · ${section.itemCount} 条经历` : ''}并加入画像` : '未发现有效内容'}</small></div><b>{section.hasContent ? '已入画像' : '待补充'}</b></div>)}{analysis.warnings.map((warning) => <div className="resume-warning" key={warning}>! {warning}</div>)}</div></section></>;
}

function AutofillView({ jobs, ready, onGenerate, onApply }: { jobs: Job[]; ready: boolean; onGenerate: () => void; onApply: (id: number) => void }) {
  return <><PageIntro eyebrow="LOCAL FILL PLAN" title="先生成草稿，再由你确认" text="这里只规划字段，不会打开招聘网站或自动提交申请。" action={<button className="primary-button" onClick={onGenerate}>生成本地填表计划</button>} /><section className="autofill-layout"><div className="panel safety-list"><div className="panel-head"><div><h2>安全边界</h2><p>真实操作始终需要你的确认</p></div></div>{[['✓', '本地生成草稿', '姓名、联系方式和经历仅在本地处理'], ['✓', '逐岗位确认', '每个岗位可单独检查字段映射'], ['—', '不会自动提交', '验证码与最终提交必须由用户完成']].map(([icon, title, text]) => <div className="safety-row" key={title}><span>{icon}</span><div><strong>{title}</strong><small>{text}</small></div></div>)}</div><div className="panel plan-card"><div className="panel-head"><div><h2>{ready ? '填表计划已生成' : '等待生成计划'}</h2><p>{ready ? `包含 ${jobs.length} 个候选岗位` : '从待确认岗位建立申请草稿'}</p></div>{ready && <span className="ready-badge">准备就绪</span>}</div>{ready ? <div className="plan-list">{jobs.map((job) => <div key={job.id}><CompanyLogo job={job} /><div><strong>{job.company} · {job.title}</strong><small>映射基本信息、教育、经历与技能 · 简历附件需确认</small></div><button onClick={() => onApply(job.id)}>{job.stage === 'applied' ? '已投递' : '确认完成'}</button></div>)}</div> : <div className="empty-state compact"><span>▤</span><h3>还没有填表计划</h3><p>点击右上角按钮生成可检查的本地草稿。</p></div>}</div></section></>;
}

function JobDrawer({ job, onClose, onPatch, onNotice }: { job: Job; onClose: () => void; onPatch: (patch: Partial<Job>) => void; onNotice: (message: string) => void }) {
  const sourceLabel = job.applySource === 'official' ? '官网岗位页' : job.applySource === 'boss' ? 'BOSS 直聘岗位页' : job.applySource === 'nowcoder' ? '牛客岗位页' : '公开平台岗位页';
  return <div className="drawer-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}><aside className="job-drawer" role="dialog" aria-modal="true" aria-label="岗位详情"><button className="drawer-close" onClick={onClose} aria-label="关闭">×</button><div className="drawer-company"><CompanyLogo job={job} /><div><p>{job.company}</p><h2>{job.title}</h2></div></div><div className="drawer-score"><strong>{job.score}%</strong><div><span>画像匹配度</span><div><i style={{ width: `${job.score}%` }} /></div></div></div><div className="drawer-facts"><span>{job.location} · {job.type}</span><span>{job.salary}</span></div><section><h3>为什么推荐给你</h3><p>{job.reason}。你的技能标签中包含 {job.tags.slice(0, 2).join('、')}，与岗位核心要求有较高重合。</p></section><section><h3>岗位简介</h3><p>{job.description}</p></section><div className="drawer-tags">{job.tags.map((tag) => <span key={tag}>{tag}</span>)}</div><p className="apply-hint"><span className={`link-source ${job.applySource === 'official' ? 'official' : ''}`}>{sourceLabel}</span>{job.applySource === 'official' ? '已核对到同一岗位的官网详情页，优先使用官网链接。' : '暂未找到已核验的官网岗位页，使用公开平台详情页。'}最终提交仍由你确认。</p><div className="drawer-actions"><button className="secondary-button danger" onClick={() => { onPatch({ dismissed: true }); onNotice('岗位已忽略，可重置演示数据恢复'); onClose(); }}>忽略岗位</button><button className="secondary-button" onClick={() => { onPatch({ saved: !job.saved, stage: job.saved ? 'matched' : 'shortlisted' }); onNotice(job.saved ? '已取消收藏' : '已加入待确认'); }}>{job.saved ? '取消收藏' : '加入待确认'}</button><button className="secondary-button" onClick={() => { onPatch({ saved: true, stage: 'applied' }); onNotice('已加入已投递阶段'); onClose(); }}>标记已投递</button><a className="primary-button apply-link" href={job.applyUrl} target="_blank" rel="noopener noreferrer" onClick={() => onNotice(`正在打开 ${job.company} 的${sourceLabel}`)}>{job.applySource === 'official' ? '前往官网投递' : `在${sourceLabel.replace('岗位页', '')}查看并投递`} <span>↗</span></a></div></aside></div>;
}
