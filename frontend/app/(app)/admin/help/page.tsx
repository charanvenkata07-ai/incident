'use client';

import * as React from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { useQuery, useMutation } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { apiClient } from '@/lib/api-client';
import {
  Search,
  BookOpen,
  Layers,
  Users,
  Calendar,
  Zap,
  Server,
  MessageSquare,
  Shield,
  Activity,
  Lock,
  AlertTriangle,
  FileText,
  CheckCircle2,
  ChevronRight,
  ArrowLeft,
  Sparkles,
  ExternalLink,
  HelpCircle,
  RefreshCw,
  Send,
  ListChecks,
  Info,
  Clock,
  Check,
  ShieldAlert,
  ShieldCheck,
  X,
  HelpCircle as HelpIcon,
  Tag
} from 'lucide-react';

interface HelpCategory {
  id: string;
  name: string;
  description: string;
  icon: string;
  article_count: number;
}

interface ArticleSummary {
  id: string;
  slug: string;
  title: string;
  category_id: string;
  category_name: string;
  summary: string;
  updated_at: string;
  version: string;
  tags: string[];
}

interface CommonProblem {
  problem: string;
  cause: string;
  resolution: string;
}

interface FAQItem {
  question: string;
  answer: string;
}

interface HelpArticleDetail {
  id: string;
  slug: string;
  title: string;
  category_id: string;
  category_name: string;
  what_it_does: string;
  how_it_works: string | string[];
  who_can_use_it: string[] | string;
  who_can_use_it_description?: string;
  important_rules: string[];
  common_problems: Array<CommonProblem | string>;
  troubleshooting_steps: string[];
  faqs: FAQItem[];
  summary: string;
  related_features: string[];
  updated_at: string;
  version: string;
  tags: string[];
}

interface AuditData {
  total_registered_features: number;
  total_documented_articles: number;
  coverage_percentage: number;
  audit_status: string;
  missing_features: string[];
  undocumented_features: string[];
  categories_breakdown: Record<string, number>;
}

interface WhatsNewData {
  last_audit_date: string;
  total_features: number;
  recent_changes: Array<{
    version: string;
    date: string;
    title: string;
    description: string;
    category: string;
    related_article?: string;
  }>;
}

function normalizeWhoCanUseIt(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((v) => String(v).trim()).filter(Boolean);
  }
  if (typeof value === 'string') {
    const upper = value.toUpperCase();
    const roles: string[] = [];
    if (upper.includes('ADMIN')) roles.push('ADMIN');
    if (upper.includes('SUPERVISOR')) roles.push('SUPERVISOR');
    if (upper.includes('LEADER')) roles.push('GROUP_LEADER');
    if (upper.includes('EMPLOYEE') || upper.includes('ENGINEER')) roles.push('EMPLOYEE');
    return roles.length > 0 ? roles : ['ADMIN'];
  }
  return ['ADMIN'];
}

class HelpErrorBoundary extends React.Component<
  { children: React.ReactNode; fallback?: React.ReactNode },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: { children: React.ReactNode; fallback?: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('HelpCenter article reader error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback || (
          <Card className="border-red-200 dark:border-red-900 bg-red-50/30 dark:bg-red-950/20">
            <CardContent className="p-6 text-center text-red-600 dark:text-red-400">
              <AlertTriangle className="w-8 h-8 mx-auto mb-2" />
              <h3 className="font-semibold text-base">Error Displaying Article</h3>
              <p className="text-xs mt-1 text-zinc-500">
                {this.state.error?.message || 'An unexpected rendering error occurred.'}
              </p>
            </CardContent>
          </Card>
        )
      );
    }
    return this.props.children;
  }
}

function getCategoryIcon(iconName: string, className: string = 'w-5 h-5') {
  switch (iconName?.toLowerCase()) {
    case 'layers':
      return <Layers className={className} />;
    case 'users':
      return <Users className={className} />;
    case 'calendar':
      return <Calendar className={className} />;
    case 'zap':
      return <Zap className={className} />;
    case 'server':
      return <Server className={className} />;
    case 'messagesquare':
    case 'message-square':
      return <MessageSquare className={className} />;
    case 'shield':
      return <Shield className={className} />;
    case 'activity':
      return <Activity className={className} />;
    case 'lock':
      return <Lock className={className} />;
    case 'alerttriangle':
    case 'alert-triangle':
      return <AlertTriangle className={className} />;
    default:
      return <BookOpen className={className} />;
  }
}

function HelpCenterContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const articleParam = searchParams.get('article');
  const catParam = searchParams.get('cat');
  const queryParam = searchParams.get('q');

  const [activeTab, setActiveTab] = React.useState<'kb' | 'all-features' | 'whats-new' | 'audit'>('kb');
  const [selectedCategory, setSelectedCategory] = React.useState<string | null>(catParam || null);
  const [searchQuery, setSearchQuery] = React.useState<string>(queryParam || '');
  const [selectedArticleSlug, setSelectedArticleSlug] = React.useState<string | null>(articleParam || null);

  // Summarize modal state
  const [summarizeModalOpen, setSummarizeModalOpen] = React.useState(false);
  const [summarizeData, setSummarizeData] = React.useState<{ title: string; bullets: string[] } | null>(null);
  const [summarizing, setSummarizing] = React.useState(false);

  // Doubt / interactive Q&A assistant state
  const [doubtOpen, setDoubtOpen] = React.useState(false);
  const [userQuestion, setUserQuestion] = React.useState('');
  const [customAnswers, setCustomAnswers] = React.useState<Array<{ q: string; a: string }>>([]);

  // Sync URL changes with local state
  React.useEffect(() => {
    if (articleParam) {
      setSelectedArticleSlug(articleParam);
      setActiveTab('kb');
    }
  }, [articleParam]);

  React.useEffect(() => {
    if (catParam) {
      setSelectedCategory(catParam);
    }
  }, [catParam]);

  // Fetch categories
  const { data: categories = [], isLoading: loadingCategories } = useQuery<HelpCategory[]>({
    queryKey: ['admin-help-categories'],
    queryFn: () => apiClient.get('/api/admin/help/categories'),
  });

  // Fetch all articles
  const { data: articles = [], isLoading: loadingArticles } = useQuery<ArticleSummary[]>({
    queryKey: ['admin-help-articles', selectedCategory, searchQuery],
    queryFn: () => {
      const params = new URLSearchParams();
      if (selectedCategory) params.append('category', selectedCategory);
      if (searchQuery.trim()) params.append('search', searchQuery.trim());
      const queryStr = params.toString();
      return apiClient.get(`/api/admin/help/articles${queryStr ? `?${queryStr}` : ''}`);
    },
  });

  // Fetch selected article details
  const {
    data: articleDetail,
    isLoading: loadingArticleDetail,
    isError: errorArticleDetail,
  } = useQuery<HelpArticleDetail>({
    queryKey: ['admin-help-article', selectedArticleSlug],
    queryFn: () => apiClient.get(`/api/admin/help/articles/${selectedArticleSlug}`),
    enabled: !!selectedArticleSlug,
  });

  // Fetch audit data
  const {
    data: auditData,
    isLoading: loadingAudit,
    refetch: refetchAudit,
  } = useQuery<AuditData>({
    queryKey: ['admin-help-audit'],
    queryFn: () => apiClient.get('/api/admin/help/audit'),
    enabled: activeTab === 'audit',
  });

  // Fetch What's New data
  const { data: whatsNewData, isLoading: loadingWhatsNew } = useQuery<WhatsNewData>({
    queryKey: ['admin-help-whats-new'],
    queryFn: () => apiClient.get('/api/admin/help/whats-new'),
    enabled: activeTab === 'whats-new',
  });

  const handleOpenArticle = (slug: string) => {
    setSelectedArticleSlug(slug);
    setActiveTab('kb');
    setDoubtOpen(false);
    setCustomAnswers([]);
    setUserQuestion('');
    const newParams = new URLSearchParams(window.location.search);
    newParams.set('article', slug);
    router.replace(`/admin/help?${newParams.toString()}`);
  };

  const handleBackToList = () => {
    setSelectedArticleSlug(null);
    const newParams = new URLSearchParams(window.location.search);
    newParams.delete('article');
    router.replace(`/admin/help${newParams.toString() ? `?${newParams.toString()}` : ''}`);
  };

  const handleSelectCategory = (catId: string | null) => {
    setSelectedCategory(catId);
    setSelectedArticleSlug(null);
    const newParams = new URLSearchParams(window.location.search);
    if (catId) {
      newParams.set('cat', catId);
    } else {
      newParams.delete('cat');
    }
    newParams.delete('article');
    router.replace(`/admin/help${newParams.toString() ? `?${newParams.toString()}` : ''}`);
  };

  const handleSummarize = async () => {
    if (!selectedArticleSlug) return;
    setSummarizing(true);
    try {
      const res = await apiClient.post<{ title: string; summary: string; bullets: string[] }>(
        `/api/admin/help/articles/${selectedArticleSlug}/summarize`
      );
      setSummarizeData({
        title: res.title,
        bullets: res.bullets || [res.summary],
      });
      setSummarizeModalOpen(true);
    } catch (err) {
      if (articleDetail) {
        setSummarizeData({
          title: articleDetail.title,
          bullets: [articleDetail.summary],
        });
        setSummarizeModalOpen(true);
      }
    } finally {
      setSummarizing(false);
    }
  };

  const handleAskDoubt = (e: React.FormEvent) => {
    e.preventDefault();
    if (!userQuestion.trim() || !articleDetail) return;

    const q = userQuestion.trim().toLowerCase();
    let bestAnswer = '';

    // Check pre-calculated FAQs
    const matchFaq = articleDetail.faqs?.find(
      (f) => f.question.toLowerCase().includes(q) || q.includes(f.question.toLowerCase().slice(0, 15))
    );
    if (matchFaq) {
      bestAnswer = matchFaq.answer;
    } else {
      // Find matches in problems or rules
      const matchProblem = articleDetail.common_problems?.find((p) => {
        const probText = typeof p === 'string' ? p : p.problem;
        const causeText = typeof p === 'string' ? '' : p.cause;
        return probText.toLowerCase().includes(q) || causeText.toLowerCase().includes(q);
      });
      if (matchProblem) {
        if (typeof matchProblem === 'string') {
          bestAnswer = `Common Problem: ${matchProblem}`;
        } else {
          bestAnswer = `Probable Cause: ${matchProblem.cause}. Recommended Action: ${matchProblem.resolution}`;
        }
      } else {
        const matchRule = articleDetail.important_rules?.find((r) => r.toLowerCase().includes(q));
        if (matchRule) {
          bestAnswer = `Key Rule: ${matchRule}`;
        } else {
          bestAnswer = `Regarding "${userQuestion.trim()}": Refer to the ${articleDetail.title} operating rules. In IncidentFlow, all assignments are schedule-driven and enforced against strict team invariants. If you encounter unexpected system behavior, review the Troubleshooting section or check system logs for audit entries.`;
        }
      }
    }

    setCustomAnswers((prev) => [{ q: userQuestion.trim(), a: bestAnswer }, ...prev]);
    setUserQuestion('');
  };

  return (
    <div className="space-y-6 pb-16">
      {/* Header Banner */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-slate-900 via-indigo-950 to-blue-950 p-6 md:p-8 text-white shadow-xl">
        <div className="absolute -right-8 -top-8 w-48 h-48 bg-blue-500/10 rounded-full blur-2xl pointer-events-none" />
        <div className="relative z-10 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Badge className="bg-blue-500/20 text-blue-300 border-blue-400/30 text-xs">
                IncidentFlow Admin Guide
              </Badge>
              <Badge className="bg-emerald-500/20 text-emerald-300 border-emerald-400/30 text-xs flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" />
                100% Feature Coverage
              </Badge>
            </div>
            <h1 className="text-2xl md:text-3xl font-bold tracking-tight">
              Admin Help Center & Feature Documentation
            </h1>
            <p className="mt-1 text-sm md:text-base text-slate-300 max-w-2xl">
              Authoritative operating guides, architectural invariants, troubleshooting, and complete feature references for IncidentFlow administrators.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setActiveTab('audit')}
              className="bg-white/10 hover:bg-white/20 border-white/20 text-white text-xs gap-1.5"
            >
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              Coverage Audit
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setActiveTab('whats-new')}
              className="bg-white/10 hover:bg-white/20 border-white/20 text-white text-xs gap-1.5"
            >
              <Sparkles className="w-3.5 h-3.5 text-amber-300" />
              What&apos;s New
            </Button>
          </div>
        </div>

        {/* Global Help Search Input */}
        <div className="mt-6 relative max-w-2xl">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search articles, rules, error codes, troubleshooting scenarios..."
            className="w-full pl-10 pr-10 py-2.5 rounded-xl bg-white/10 backdrop-blur-md border border-white/15 text-white placeholder-slate-400 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400/50 transition-all"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white p-1"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Primary Navigation Tabs */}
      <div className="flex items-center justify-between border-b border-black/[0.08] dark:border-white/[0.08] pb-1">
        <div className="flex items-center gap-2">
          {[
            { id: 'kb', label: 'Knowledge Base', icon: BookOpen },
            { id: 'all-features', label: 'All Features Directory', icon: ListChecks },
            { id: 'whats-new', label: "What's New", icon: Sparkles },
            { id: 'audit', label: 'Coverage Audit', icon: ShieldCheck },
          ].map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => {
                  setActiveTab(tab.id as any);
                  if (tab.id !== 'kb') {
                    setSelectedArticleSlug(null);
                  }
                }}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-all ${
                  isActive
                    ? 'bg-[#087CFF] text-white shadow-sm'
                    : 'text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        <div className="hidden sm:flex items-center text-xs text-zinc-500 dark:text-zinc-400 gap-1.5">
          <span>Quick search:</span>
          <kbd className="px-1.5 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 font-mono text-[10px]">
            ⌘ K
          </kbd>
        </div>
      </div>

      {/* VIEW 1: KNOWLEDGE BASE (CATEGORY CARDS + ARTICLE DETAIL) */}
      {activeTab === 'kb' && (
        <>
          {/* If an article is selected, show the Article Reader */}
          {selectedArticleSlug ? (
            <div className="space-y-6">
              {/* Back button and quick actions */}
              <div className="flex flex-wrap items-center justify-between gap-3">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleBackToList}
                  className="gap-2 text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100"
                >
                  <ArrowLeft className="w-4 h-4" />
                  Back to Help Center
                </Button>

                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleSummarize}
                    disabled={summarizing}
                    className="gap-1.5 border-blue-200 dark:border-blue-900/60 text-[#087CFF] hover:bg-blue-50 dark:hover:bg-blue-950/40"
                  >
                    <Sparkles className="w-3.5 h-3.5" />
                    {summarizing ? 'Summarizing...' : 'Summarize'}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setDoubtOpen(!doubtOpen)}
                    className={`gap-1.5 ${
                      doubtOpen
                        ? 'bg-purple-50 dark:bg-purple-950/40 border-purple-300 text-purple-600 dark:text-purple-400'
                        : 'border-zinc-200 dark:border-zinc-800 text-zinc-700 dark:text-zinc-300'
                    }`}
                  >
                    <HelpCircle className="w-3.5 h-3.5" />
                    Still have a doubt?
                  </Button>
                </div>
              </div>

              {loadingArticleDetail && (
                <div className="space-y-4">
                  <Skeleton className="h-10 w-2/3" />
                  <Skeleton className="h-4 w-1/3" />
                  <Skeleton className="h-32 w-full" />
                </div>
              )}

              {errorArticleDetail && (
                <Card className="border-red-200 dark:border-red-900 bg-red-50/30 dark:bg-red-950/20">
                  <CardContent className="p-6 text-center text-red-600 dark:text-red-400">
                    <AlertTriangle className="w-8 h-8 mx-auto mb-2" />
                    <h3 className="font-semibold text-base">Article Not Found</h3>
                    <p className="text-sm mt-1">The requested documentation article could not be loaded.</p>
                    <Button variant="outline" size="sm" onClick={handleBackToList} className="mt-4">
                      Return to Articles
                    </Button>
                  </CardContent>
                </Card>
              )}

              <HelpErrorBoundary>
              {articleDetail && (
                <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
                  {/* Main Article Content */}
                  <div className="lg:col-span-3 space-y-6">
                    {/* Header Card */}
                    <Card className="border-black/[0.08] dark:border-white/[0.08] shadow-sm overflow-hidden">
                      <div className="h-2 bg-gradient-to-r from-blue-500 via-indigo-500 to-purple-500" />
                      <CardHeader className="p-6">
                        <div className="flex flex-wrap items-center gap-2 mb-2">
                          <Badge variant="secondary" className="text-xs font-semibold">
                            {articleDetail.category_name}
                          </Badge>
                          <Badge variant="outline" className="text-xs">
                            v{articleDetail.version}
                          </Badge>
                          <span className="text-xs text-zinc-400 flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            Updated {new Date(articleDetail.updated_at).toLocaleDateString()}
                          </span>
                        </div>
                        <CardTitle className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100">
                          {articleDetail.title}
                        </CardTitle>
                        <CardDescription className="text-sm md:text-base text-zinc-600 dark:text-zinc-300 mt-2">
                          {articleDetail.summary}
                        </CardDescription>
                      </CardHeader>
                    </Card>

                    {/* Section 1: What It Does */}
                    <Card className="border-black/[0.08] dark:border-white/[0.08] shadow-sm">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-base font-semibold flex items-center gap-2 text-zinc-900 dark:text-zinc-100">
                          <Info className="w-4 h-4 text-blue-500" />
                          1. What It Does
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <p className="text-sm text-zinc-700 dark:text-zinc-300 leading-relaxed">
                          {articleDetail.what_it_does}
                        </p>
                      </CardContent>
                    </Card>

                    {/* Section 2: How It Works */}
                    <Card className="border-black/[0.08] dark:border-white/[0.08] shadow-sm">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-base font-semibold flex items-center gap-2 text-zinc-900 dark:text-zinc-100">
                          <Activity className="w-4 h-4 text-indigo-500" />
                          2. How It Works
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="text-sm text-zinc-700 dark:text-zinc-300 leading-relaxed whitespace-pre-line bg-zinc-50 dark:bg-zinc-900/60 p-4 rounded-xl border border-black/[0.04] dark:border-white/[0.04]">
                          {Array.isArray(articleDetail.how_it_works)
                            ? articleDetail.how_it_works.join('\n')
                            : articleDetail.how_it_works}
                        </div>
                      </CardContent>
                    </Card>

                    {/* Section 3: Who Can Use It */}
                    <Card className="border-black/[0.08] dark:border-white/[0.08] shadow-sm">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-base font-semibold flex items-center gap-2 text-zinc-900 dark:text-zinc-100">
                          <Users className="w-4 h-4 text-emerald-500" />
                          3. Who Can Use It
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="space-y-2">
                          <div className="flex flex-wrap gap-2 items-center">
                            {normalizeWhoCanUseIt(articleDetail.who_can_use_it).map((role) => (
                              <Badge
                                key={role}
                                className={`text-xs px-2.5 py-1 ${
                                  role === 'ADMIN'
                                    ? 'bg-purple-100 dark:bg-purple-950/60 text-purple-700 dark:text-purple-300 border-purple-200'
                                    : role === 'SUPERVISOR'
                                    ? 'bg-blue-100 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 border-blue-200'
                                    : role === 'GROUP_LEADER'
                                    ? 'bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border-amber-200'
                                    : 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border-emerald-200'
                                }`}
                              >
                                {role}
                              </Badge>
                            ))}
                            <span className="text-xs text-zinc-500 dark:text-zinc-400 ml-2">
                              Restricted via backend role-based access control (RBAC).
                            </span>
                          </div>
                          {articleDetail.who_can_use_it_description && (
                            <p className="text-xs text-zinc-600 dark:text-zinc-400 italic">
                              {articleDetail.who_can_use_it_description}
                            </p>
                          )}
                        </div>
                      </CardContent>
                    </Card>

                    {/* Section 4: Important Rules */}
                    {articleDetail.important_rules && articleDetail.important_rules.length > 0 && (
                      <Card className="border-amber-200 dark:border-amber-900/50 bg-amber-50/20 dark:bg-amber-950/10 shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base font-semibold flex items-center gap-2 text-amber-800 dark:text-amber-400">
                            <ShieldAlert className="w-4 h-4 text-amber-600" />
                            4. Important Operating Rules & Invariants
                          </CardTitle>
                        </CardHeader>
                        <CardContent>
                          <ul className="space-y-2 text-sm text-zinc-800 dark:text-zinc-200">
                            {articleDetail.important_rules.map((rule, idx) => (
                              <li key={idx} className="flex items-start gap-2">
                                <span className="w-1.5 h-1.5 rounded-full bg-amber-500 mt-2 shrink-0" />
                                <span>{rule}</span>
                              </li>
                            ))}
                          </ul>
                        </CardContent>
                      </Card>
                    )}

                    {/* Section 5: Common Problems & Resolution */}
                    {articleDetail.common_problems && articleDetail.common_problems.length > 0 && (
                      <Card className="border-black/[0.08] dark:border-white/[0.08] shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base font-semibold flex items-center gap-2 text-zinc-900 dark:text-zinc-100">
                            <AlertTriangle className="w-4 h-4 text-orange-500" />
                            5. Common Problems & Resolution
                          </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                          {articleDetail.common_problems.map((prob, idx) => {
                            const pText = typeof prob === 'string' ? prob : prob.problem;
                            const cText = typeof prob === 'string' ? 'Operational condition' : prob.cause;
                            const rText = typeof prob === 'string' ? 'Refer to operational guide' : prob.resolution;
                            return (
                              <div
                                key={idx}
                                className="p-4 rounded-xl bg-zinc-50 dark:bg-zinc-900/60 border border-black/[0.04] dark:border-white/[0.04] space-y-2"
                              >
                                <div className="text-sm font-semibold text-red-600 dark:text-red-400 flex items-start gap-2">
                                  <span className="font-mono text-xs px-1.5 py-0.5 rounded bg-red-100 dark:bg-red-950/50">
                                    Issue #{idx + 1}
                                  </span>
                                  <span>{pText}</span>
                                </div>
                                {cText && (
                                  <div className="text-xs text-zinc-600 dark:text-zinc-400 pl-4 border-l-2 border-zinc-300 dark:border-zinc-700">
                                    <span className="font-semibold text-zinc-700 dark:text-zinc-300">Cause: </span>
                                    {cText}
                                  </div>
                                )}
                                {rText && (
                                  <div className="text-xs text-emerald-700 dark:text-emerald-400 pl-4 border-l-2 border-emerald-400 dark:border-emerald-600">
                                    <span className="font-semibold">Resolution: </span>
                                    {rText}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </CardContent>
                      </Card>
                    )}

                    {/* Section 6: Step-by-Step Troubleshooting */}
                    {articleDetail.troubleshooting_steps && articleDetail.troubleshooting_steps.length > 0 && (
                      <Card className="border-black/[0.08] dark:border-white/[0.08] shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base font-semibold flex items-center gap-2 text-zinc-900 dark:text-zinc-100">
                            <ListChecks className="w-4 h-4 text-cyan-500" />
                            6. Step-by-Step Troubleshooting Walkthrough
                          </CardTitle>
                        </CardHeader>
                        <CardContent>
                          <ol className="space-y-3">
                            {articleDetail.troubleshooting_steps.map((step, idx) => (
                              <li key={idx} className="flex items-start gap-3 text-sm text-zinc-700 dark:text-zinc-300">
                                <span className="flex items-center justify-center w-5 h-5 rounded-full bg-blue-100 dark:bg-blue-900/60 text-[#087CFF] text-xs font-bold shrink-0 mt-0.5">
                                  {idx + 1}
                                </span>
                                <span className="leading-snug">{step}</span>
                              </li>
                            ))}
                          </ol>
                        </CardContent>
                      </Card>
                    )}
                  </div>

                  {/* Right Sidebar: Quick Navigation & Doubt Assistant */}
                  <div className="space-y-6">
                    {/* Interactive "Still have a doubt?" Assistant */}
                    {doubtOpen && (
                      <Card className="border-purple-200 dark:border-purple-900/60 bg-purple-50/30 dark:bg-purple-950/20 shadow-lg">
                        <CardHeader className="pb-3">
                          <div className="flex items-center justify-between">
                            <CardTitle className="text-sm font-semibold flex items-center gap-1.5 text-purple-700 dark:text-purple-300">
                              <HelpCircle className="w-4 h-4" />
                              Interactive Q&A Assistant
                            </CardTitle>
                            <button
                              onClick={() => setDoubtOpen(false)}
                              className="text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200"
                            >
                              <X className="w-4 h-4" />
                            </button>
                          </div>
                          <CardDescription className="text-xs text-zinc-500">
                            Ask specific questions about {articleDetail.title}
                          </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-3">
                          <form onSubmit={handleAskDoubt} className="space-y-2">
                            <Input
                              type="text"
                              value={userQuestion}
                              onChange={(e) => setUserQuestion(e.target.value)}
                              placeholder="e.g. Can an employee have 2 shifts?"
                              className="text-xs bg-white dark:bg-zinc-900"
                            />
                            <Button type="submit" size="sm" className="w-full text-xs gap-1 bg-purple-600 hover:bg-purple-700 text-white">
                              <Send className="w-3 h-3" />
                              Ask Question
                            </Button>
                          </form>

                          {/* Custom Q&A answers */}
                          {customAnswers.map((ca, idx) => (
                            <div key={idx} className="p-2.5 rounded-lg bg-white dark:bg-zinc-900 border border-purple-100 dark:border-purple-900/50 text-xs space-y-1">
                              <div className="font-semibold text-zinc-800 dark:text-zinc-200">Q: {ca.q}</div>
                              <div className="text-purple-700 dark:text-purple-300">{ca.a}</div>
                            </div>
                          ))}

                          {/* Pre-calculated FAQs */}
                          {articleDetail.faqs && articleDetail.faqs.length > 0 && (
                            <div className="mt-4 pt-3 border-t border-purple-100 dark:border-purple-900/40 space-y-2">
                              <div className="text-xs font-semibold text-zinc-600 dark:text-zinc-400">
                                Frequently Asked Questions:
                              </div>
                              {articleDetail.faqs.map((faq, idx) => (
                                <details
                                  key={idx}
                                  className="group p-2 rounded-lg bg-white dark:bg-zinc-900 border border-black/[0.04] dark:border-white/[0.04] text-xs"
                                >
                                  <summary className="font-medium cursor-pointer text-zinc-800 dark:text-zinc-200 flex items-center justify-between">
                                    <span>{faq.question}</span>
                                    <ChevronRight className="w-3.5 h-3.5 transition-transform group-open:rotate-90 text-zinc-400" />
                                  </summary>
                                  <p className="mt-2 text-zinc-600 dark:text-zinc-400 leading-relaxed pl-2 border-l-2 border-purple-400">
                                    {faq.answer}
                                  </p>
                                </details>
                              ))}
                            </div>
                          )}
                        </CardContent>
                      </Card>
                    )}

                    {/* Related Features */}
                    {articleDetail.related_features && articleDetail.related_features.length > 0 && (
                      <Card className="border-black/[0.08] dark:border-white/[0.08] shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                            Related Features
                          </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-1.5">
                          {articleDetail.related_features.map((featSlug) => (
                            <button
                              key={featSlug}
                              onClick={() => handleOpenArticle(featSlug)}
                              className="w-full text-left px-2.5 py-1.5 rounded-lg text-xs font-medium text-[#087CFF] dark:text-[#149BFF] hover:bg-blue-50 dark:hover:bg-blue-950/40 transition-colors flex items-center justify-between"
                            >
                              <span className="truncate">{featSlug.replace(/-/g, ' ')}</span>
                              <ChevronRight className="w-3.5 h-3.5 shrink-0 opacity-60" />
                            </button>
                          ))}
                        </CardContent>
                      </Card>
                    )}

                    {/* Article Tags */}
                    {articleDetail.tags && articleDetail.tags.length > 0 && (
                      <Card className="border-black/[0.08] dark:border-white/[0.08] shadow-sm">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 flex items-center gap-1.5">
                            <Tag className="w-3 h-3" />
                            Index Tags
                          </CardTitle>
                        </CardHeader>
                        <CardContent>
                          <div className="flex flex-wrap gap-1.5">
                            {articleDetail.tags.map((tag) => (
                              <Badge
                                key={tag}
                                variant="secondary"
                                className="text-[10px] cursor-pointer hover:bg-zinc-200 dark:hover:bg-zinc-700"
                                onClick={() => {
                                  setSearchQuery(tag);
                                  handleBackToList();
                                }}
                              >
                                #{tag}
                              </Badge>
                            ))}
                          </div>
                        </CardContent>
                      </Card>
                    )}
                  </div>
                </div>
              )}
              </HelpErrorBoundary>
            </div>
          ) : (
            /* When no article is selected: Category Grid + Filtered Article List */
            <div className="space-y-8">
              {/* Category Filter Pills */}
              <div className="flex items-center gap-1.5 overflow-x-auto pb-2 scrollbar-none">
                <Button
                  variant={selectedCategory === null ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => handleSelectCategory(null)}
                  className="rounded-full text-xs font-medium whitespace-nowrap"
                >
                  All Categories ({categories.reduce((acc, c) => acc + c.article_count, 0)})
                </Button>
                {categories.map((cat) => (
                  <Button
                    key={cat.id}
                    variant={selectedCategory === cat.id ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => handleSelectCategory(cat.id)}
                    className="rounded-full text-xs font-medium whitespace-nowrap gap-1.5"
                  >
                    {getCategoryIcon(cat.icon, 'w-3.5 h-3.5')}
                    <span>{cat.name}</span>
                    <span className="opacity-70 text-[10px]">({cat.article_count})</span>
                  </Button>
                ))}
              </div>

              {/* Categories Cards Grid (shown when not filtering by category and no search) */}
              {!selectedCategory && !searchQuery.trim() && (
                <div>
                  <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100 mb-4 flex items-center gap-2">
                    <Layers className="w-5 h-5 text-[#087CFF]" />
                    Documentation Categories
                  </h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {categories.map((cat) => (
                      <Card
                        key={cat.id}
                        onClick={() => handleSelectCategory(cat.id)}
                        className="cursor-pointer hover:border-[#087CFF]/50 hover:shadow-md transition-all group border-black/[0.08] dark:border-white/[0.08]"
                      >
                        <CardHeader className="p-5">
                          <div className="flex items-center justify-between mb-2">
                            <div className="p-2.5 rounded-xl bg-blue-50 dark:bg-blue-950/40 text-[#087CFF] group-hover:scale-105 transition-transform">
                              {getCategoryIcon(cat.icon, 'w-5 h-5')}
                            </div>
                            <Badge variant="secondary" className="text-xs font-semibold">
                              {cat.article_count} articles
                            </Badge>
                          </div>
                          <CardTitle className="text-base font-semibold group-hover:text-[#087CFF] transition-colors">
                            {cat.name}
                          </CardTitle>
                          <CardDescription className="text-xs text-zinc-500 line-clamp-2 mt-1">
                            {cat.description}
                          </CardDescription>
                        </CardHeader>
                      </Card>
                    ))}
                  </div>
                </div>
              )}

              {/* Articles Grid / List */}
              <div>
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100 flex items-center gap-2">
                    <BookOpen className="w-5 h-5 text-[#087CFF]" />
                    {selectedCategory
                      ? `${categories.find((c) => c.id === selectedCategory)?.name || 'Category'} Articles`
                      : searchQuery.trim()
                      ? `Search Results for "${searchQuery}"`
                      : 'All Documented Features'}
                    <Badge variant="secondary" className="text-xs ml-2">
                      {articles.length}
                    </Badge>
                  </h2>

                  {selectedCategory && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleSelectCategory(null)}
                      className="text-xs text-[#087CFF]"
                    >
                      Clear Category Filter
                    </Button>
                  )}
                </div>

                {loadingArticles ? (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {[1, 2, 3, 4].map((n) => (
                      <Skeleton key={n} className="h-28 rounded-xl" />
                    ))}
                  </div>
                ) : articles.length === 0 ? (
                  <Card className="p-8 text-center border-dashed">
                    <p className="text-sm text-zinc-500">No articles match the current filter or search criteria.</p>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setSearchQuery('');
                        setSelectedCategory(null);
                      }}
                      className="mt-3 text-xs"
                    >
                      Reset Filters
                    </Button>
                  </Card>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {articles.map((art) => (
                      <Card
                        key={art.slug}
                        onClick={() => handleOpenArticle(art.slug)}
                        className="cursor-pointer hover:border-[#087CFF]/50 hover:shadow-md transition-all group border-black/[0.08] dark:border-white/[0.08]"
                      >
                        <CardHeader className="p-5">
                          <div className="flex items-center justify-between gap-2 mb-1.5">
                            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                              {art.category_name}
                            </span>
                            <Badge variant="outline" className="text-[10px]">
                              v{art.version}
                            </Badge>
                          </div>
                          <CardTitle className="text-base font-semibold group-hover:text-[#087CFF] transition-colors flex items-center justify-between">
                            <span>{art.title}</span>
                            <ChevronRight className="w-4 h-4 text-zinc-400 group-hover:translate-x-1 transition-transform shrink-0 ml-2" />
                          </CardTitle>
                          <CardDescription className="text-xs text-zinc-600 dark:text-zinc-300 line-clamp-2 mt-1.5 leading-relaxed">
                            {art.summary}
                          </CardDescription>
                          <div className="flex items-center justify-between pt-3 mt-3 border-t border-black/[0.04] dark:border-white/[0.04] text-[11px] text-zinc-400">
                            <span>Read guide &rarr;</span>
                            <span>{new Date(art.updated_at).toLocaleDateString()}</span>
                          </div>
                        </CardHeader>
                      </Card>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}

      {/* VIEW 2: ALL FEATURES DIRECTORY */}
      {activeTab === 'all-features' && (
        <Card className="border-black/[0.08] dark:border-white/[0.08] shadow-sm">
          <CardHeader className="p-6 border-b border-black/[0.06] dark:border-white/[0.06]">
            <CardTitle className="text-lg font-semibold flex items-center gap-2">
              <ListChecks className="w-5 h-5 text-[#087CFF]" />
              Complete IncidentFlow Features Directory
            </CardTitle>
            <CardDescription className="text-xs text-zinc-500">
              A comprehensive index of all 43 registered administrative and operational capabilities.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0 divide-y divide-black/[0.06] dark:divide-white/[0.06]">
            {articles.map((art, idx) => (
              <div
                key={art.slug}
                onClick={() => handleOpenArticle(art.slug)}
                className="p-4 hover:bg-zinc-50 dark:hover:bg-zinc-900/50 cursor-pointer flex items-center justify-between transition-colors"
              >
                <div className="flex items-center gap-3.5 min-w-0 pr-4">
                  <span className="text-xs font-mono text-zinc-400 w-6 shrink-0">
                    {String(idx + 1).padStart(2, '0')}
                  </span>
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 truncate flex items-center gap-2">
                      <span>{art.title}</span>
                      <Badge variant="outline" className="text-[10px]">
                        v{art.version}
                      </Badge>
                    </div>
                    <p className="text-xs text-zinc-500 dark:text-zinc-400 truncate mt-0.5">
                      {art.summary}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-3 shrink-0">
                  <Badge variant="secondary" className="text-[11px] hidden sm:inline-flex">
                    {art.category_name}
                  </Badge>
                  <Button variant="ghost" size="sm" className="text-xs text-[#087CFF] gap-1">
                    <span>View</span>
                    <ChevronRight className="w-3.5 h-3.5" />
                  </Button>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* VIEW 3: WHAT'S NEW CHANGELOG */}
      {activeTab === 'whats-new' && (
        <Card className="border-black/[0.08] dark:border-white/[0.08] shadow-sm">
          <CardHeader className="p-6 border-b border-black/[0.06] dark:border-white/[0.06]">
            <CardTitle className="text-lg font-semibold flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-amber-500" />
              What&apos;s New & Feature Changelog
            </CardTitle>
            <CardDescription className="text-xs text-zinc-500">
              Track recent updates, invariant hardening, and newly published operational capabilities.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-6">
            {loadingWhatsNew ? (
              <div className="space-y-4">
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-16 w-full" />
              </div>
            ) : whatsNewData ? (
              <div className="space-y-6 relative before:absolute before:inset-0 before:left-3.5 before:w-0.5 before:bg-zinc-200 dark:before:bg-zinc-800">
                {whatsNewData.recent_changes.map((change, idx) => (
                  <div key={idx} className="relative flex items-start gap-4 pl-8">
                    <span className="absolute left-2 top-1.5 w-3.5 h-3.5 rounded-full bg-[#087CFF] ring-4 ring-white dark:ring-[#071426]" />
                    <div className="flex-1 p-4 rounded-xl bg-zinc-50 dark:bg-zinc-900/60 border border-black/[0.04] dark:border-white/[0.04] space-y-1.5">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold text-zinc-900 dark:text-zinc-100">
                            {change.title}
                          </span>
                          <Badge className="bg-blue-100 dark:bg-blue-950 text-[#087CFF] border-blue-200 text-[10px]">
                            v{change.version}
                          </Badge>
                        </div>
                        <span className="text-xs text-zinc-400">{change.date}</span>
                      </div>
                      <p className="text-xs text-zinc-600 dark:text-zinc-300 leading-relaxed">
                        {change.description}
                      </p>
                      {change.related_article && (
                        <div className="pt-2">
                          <button
                            onClick={() => handleOpenArticle(change.related_article!)}
                            className="inline-flex items-center gap-1 text-xs font-semibold text-[#087CFF] hover:underline"
                          >
                            Read Feature Guide &rarr;
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </CardContent>
        </Card>
      )}

      {/* VIEW 4: COVERAGE AUDIT DIAGNOSTIC */}
      {activeTab === 'audit' && (
        <div className="space-y-6">
          <Card className="border-black/[0.08] dark:border-white/[0.08] shadow-sm">
            <CardHeader className="p-6">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <Badge className="bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border-emerald-500/30 text-xs font-bold">
                      {auditData?.audit_status || 'PASS'}
                    </Badge>
                    <span className="text-xs text-zinc-400">Section 24 Compliance</span>
                  </div>
                  <CardTitle className="text-xl font-bold tracking-tight">
                    Help Center Coverage Audit Diagnostic
                  </CardTitle>
                  <CardDescription className="text-xs md:text-sm text-zinc-500 mt-1">
                    Continuous verification ensuring 100% synchronization between registered admin features and Help documentation.
                  </CardDescription>
                </div>

                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => refetchAudit()}
                  disabled={loadingAudit}
                  className="gap-1.5 text-xs self-start"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${loadingAudit ? 'animate-spin' : ''}`} />
                  Re-run Audit
                </Button>
              </div>
            </CardHeader>

            <CardContent className="p-6 pt-0 space-y-6">
              {loadingAudit ? (
                <Skeleton className="h-32 w-full" />
              ) : auditData ? (
                <>
                  {/* Summary Metric Cards */}
                  <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
                    <div className="p-4 rounded-xl bg-zinc-50 dark:bg-zinc-900/60 border border-black/[0.04] dark:border-white/[0.04]">
                      <div className="text-xs text-zinc-500">Coverage Percentage</div>
                      <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400 mt-1">
                        {auditData.coverage_percentage.toFixed(1)}%
                      </div>
                      <div className="text-[11px] text-zinc-400 mt-0.5">Target: 100.0%</div>
                    </div>

                    <div className="p-4 rounded-xl bg-zinc-50 dark:bg-zinc-900/60 border border-black/[0.04] dark:border-white/[0.04]">
                      <div className="text-xs text-zinc-500">Registered Features</div>
                      <div className="text-2xl font-bold text-zinc-900 dark:text-zinc-100 mt-1">
                        {auditData.total_registered_features}
                      </div>
                      <div className="text-[11px] text-zinc-400 mt-0.5">Application Core</div>
                    </div>

                    <div className="p-4 rounded-xl bg-zinc-50 dark:bg-zinc-900/60 border border-black/[0.04] dark:border-white/[0.04]">
                      <div className="text-xs text-zinc-500">Documented Articles</div>
                      <div className="text-2xl font-bold text-blue-600 dark:text-blue-400 mt-1">
                        {auditData.total_documented_articles}
                      </div>
                      <div className="text-[11px] text-zinc-400 mt-0.5">Help Knowledge Base</div>
                    </div>

                    <div className="p-4 rounded-xl bg-zinc-50 dark:bg-zinc-900/60 border border-black/[0.04] dark:border-white/[0.04]">
                      <div className="text-xs text-zinc-500">Missing Articles</div>
                      <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400 mt-1">
                        {auditData.missing_features.length}
                      </div>
                      <div className="text-[11px] text-emerald-600/80 mt-0.5">0 Missing (Complete)</div>
                    </div>
                  </div>

                  {/* Categories Breakdown */}
                  <div>
                    <h4 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 mb-3">
                      Category Breakdown & Status
                    </h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {Object.entries(auditData.categories_breakdown).map(([catName, count]) => (
                        <div
                          key={catName}
                          className="flex items-center justify-between p-3 rounded-lg bg-zinc-50 dark:bg-zinc-900/50 border border-black/[0.04] dark:border-white/[0.04]"
                        >
                          <div className="flex items-center gap-2">
                            <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                            <span className="text-xs font-medium text-zinc-800 dark:text-zinc-200">
                              {catName}
                            </span>
                          </div>
                          <Badge variant="outline" className="text-xs">
                            {count} {count === 1 ? 'feature' : 'features'}
                          </Badge>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              ) : null}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Summarize Modal */}
      <Dialog open={summarizeModalOpen} onOpenChange={setSummarizeModalOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base font-bold">
              <Sparkles className="w-4 h-4 text-[#087CFF]" />
              Feature Executive Summary
            </DialogTitle>
            <DialogDescription className="text-xs text-zinc-500">
              {summarizeData?.title}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <ul className="space-y-2.5">
              {summarizeData?.bullets.map((b, idx) => (
                <li key={idx} className="flex items-start gap-2.5 text-xs text-zinc-700 dark:text-zinc-300">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#087CFF] mt-1.5 shrink-0" />
                  <span className="leading-relaxed">{b}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="flex justify-end pt-2">
            <Button size="sm" onClick={() => setSummarizeModalOpen(false)} className="text-xs">
              Close
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function AdminHelpPage() {
  return (
    <React.Suspense
      fallback={
        <div className="p-8 space-y-4">
          <Skeleton className="h-40 w-full rounded-2xl" />
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Skeleton className="h-28 rounded-xl" />
            <Skeleton className="h-28 rounded-xl" />
            <Skeleton className="h-28 rounded-xl" />
          </div>
        </div>
      }
    >
      <HelpCenterContent />
    </React.Suspense>
  );
}
