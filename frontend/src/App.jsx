import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertCircle, ArrowRight, Briefcase, Check, CheckCircle2, ChevronDown, ChevronUp,
  FileCheck2, FileText, Github, Gauge, Linkedin, ListChecks, LoaderCircle, Mail,
  MessageSquareText, Phone, RotateCcw, ShieldAlert, Sparkles, Upload, X,
} from 'lucide-react'

const MAX_BYTES = 5 * 1024 * 1024
const wordTokens = (text) => text.match(/[A-Za-z][A-Za-z+#./'-]*/g) || []
const stopWords = new Set('a an the and or of to in for with on at by from as is are be this that will you your we our their it its i they them who what when where which while how work working team teams ability strong skills skill years year etc including preferred required plus role job candidate must have has can able good great new using use based across within into such other more also any all not looking join company position responsibilities requirements qualifications hiring manage seeking opportunity knowledge understanding familiarity well need needs ensure support help make develop'.split(' '))

function quickCheck(text) {
  const words = wordTokens(text)
  if (words.length < 80) return { valid: false, message: `Add at least 80 words. You have ${words.length} so far.` }
  const lower = text.toLowerCase()
  if (/\b(lorem|ipsum|dolor|consectetur|adipiscing|elit)\b/.test(lower)) return { valid: false, message: 'Placeholder text detected. Paste the actual job description.' }
  if (/(.)\1{5,}/i.test(text)) return { valid: false, message: 'Repeated characters detected. Replace them with readable job-posting text.' }
  const contentWords = words.map(w => w.toLowerCase().replace(/^['./-]+|['./-]+$/g, '')).filter(w => w.length > 2 && !stopWords.has(w))
  const counts = contentWords.reduce((a, w) => (a[w] = (a[w] || 0) + 1, a), {})
  const ranked = Object.values(counts).sort((a, b) => b - a)
  if (contentWords.length && ((ranked[0] || 0) / contentWords.length > .12 || ranked.slice(0, 3).reduce((a, n) => a + n, 0) / contentWords.length > .30)) return { valid: false, message: 'The same words repeat too often. Paste a complete, readable job description.' }
  const signals = ['responsibilit', 'duties', 'accountabilities', 'qualification', 'requirements', 'required', 'must have', 'experience', 'years', 'background', 'role', 'position', 'candidate', 'develop', 'build', 'design', 'manage', 'lead', 'analyze', 'implement', 'maintain', 'deliver', 'collaborate', 'create', 'support', 'own', 'drive']
  if (new Set(signals.filter(s => lower.includes(s))).size < 3) return { valid: false, message: 'Add job responsibilities, qualifications, experience, and role-specific requirements.' }
  return { valid: null, message: 'Checking readability and job-related skills…' }
}

async function readApiResponse(response) {
  const text = await response.text()
  try {
    return JSON.parse(text)
  } catch {
    if (!response.ok) throw new Error(`The analyzer could not complete the request (HTTP ${response.status}). Check that the API terminal has no errors, then try again.`)
    throw new Error('The analyzer returned an unreadable response. Please try again.')
  }
}
const priorityClass = (priority = 'Medium') => ({ High: 'priority-high', Medium: 'priority-medium', Low: 'priority-low' }[priority] || 'priority-medium')

function App() {
  const [file, setFile] = useState(null)
  const [jd, setJd] = useState('')
  const [validation, setValidation] = useState({ valid: false, message: 'Paste a complete job description to begin.' })
  const [llmAvailable, setLlmAvailable] = useState(false)
  const [useLlm, setUseLlm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [open, setOpen] = useState({ breakdown: true, details: false, safety: false, interview: false })
  const [votes, setVotes] = useState(() => { try { return JSON.parse(localStorage.getItem('rolefit-feedback') || '{}') } catch { return {} } })
  const inputRef = useRef(null)
  const controllerRef = useRef(null)
  const words = wordTokens(jd).length

  useEffect(() => {
    fetch('/api/health').then(r => r.json()).then(d => setLlmAvailable(Boolean(d.llm_available))).catch(() => {})
  }, [])

  useEffect(() => {
    if (!jd.trim()) { setValidation({ valid: false, message: 'Paste a complete job description to begin.' }); return }
    const local = quickCheck(jd)
    if (local.valid === false) { setValidation(local); return }
    const controller = new AbortController()
    controllerRef.current?.abort()
    controllerRef.current = controller
    const timer = setTimeout(async () => {
      try {
        const body = new FormData(); body.append('job_description', jd)
        const response = await fetch('/api/validate-jd', { method: 'POST', body, signal: controller.signal })
        const data = await readApiResponse(response)
        setValidation({ valid: data.valid, message: data.message })
      } catch (e) {
        if (e.name !== 'AbortError') setValidation({ valid: null, message: 'Live check unavailable. The server will still validate before analysis.' })
      }
    }, 500)
    return () => { clearTimeout(timer); controller.abort() }
  }, [jd])

  const ready = useMemo(() => Boolean(file && words >= 80 && validation.valid === true && !busy), [file, words, validation.valid, busy])

  function chooseFile(next) {
    if (!next) return
    setError('')
    const ext = next.name.toLowerCase().split('.').pop()
    if (!['pdf', 'docx'].includes(ext)) { setFile(null); setError('Upload your resume as a PDF or DOCX file.'); return }
    if (next.size > MAX_BYTES) { setFile(null); setError('This file is larger than 5 MB. Choose a smaller resume.'); return }
    setFile(next)
  }

  async function analyze(event) {
    event.preventDefault()
    if (!ready) return
    setBusy(true); setError('')
    const body = new FormData()
    body.append('resume', file)
    body.append('job_description', jd)
    body.append('use_llm', String(useLlm))
    try {
      const response = await fetch('/api/analyze', { method: 'POST', body })
      const data = await readApiResponse(response)
      if (!response.ok) throw new Error(data.detail || 'The analysis could not be completed. Please try again.')
      setResult(data)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (e) { setError(e.message || 'Could not reach the analyzer. Check that the API server is running.') }
    finally { setBusy(false) }
  }

  function vote(category, value) {
    const next = { ...votes, [category]: value }
    setVotes(next)
    try { localStorage.setItem('rolefit-feedback', JSON.stringify(next)) } catch { /* Private mode may disable storage. */ }
  }

  const recommendations = useMemo(() => {
    if (!result) return []
    return [...result.recommendations].sort((a, b) => {
      const order = { High: 0, Medium: 1, Low: 2 }
      const priority = order[a.priority] - order[b.priority]
      if (priority) return priority
      return (votes[b.category] === 'helpful' ? 1 : 0) - (votes[a.category] === 'helpful' ? 1 : 0)
    })
  }, [result, votes])

  function reset() { setResult(null); setFile(null); setJd(''); setError(''); setUseLlm(false); if (inputRef.current) inputRef.current.value = ''; window.scrollTo({ top: 0, behavior: 'smooth' }) }

  return <main className="min-h-screen px-4 pb-20 sm:px-6">
    <div className="mx-auto max-w-6xl">
      <header className="flex h-[76px] items-center justify-between border-b border-white/[.08]">
        <a href="#top" className="flex items-center gap-3 text-sm font-semibold tracking-wide text-zinc-100" id="top">
          <span className="grid h-8 w-8 place-items-center rounded-lg border border-white/10 bg-white/[.04] text-blue-200"><FileCheck2 size={16} /></span>
          ROLEFIT <span className="hidden text-zinc-500 sm:inline">/ RESUME INTELLIGENCE</span>
        </a>
        <span className="flex items-center gap-2 rounded-full border border-white/10 px-3 py-1.5 text-[11px] text-zinc-400"><span className="h-1.5 w-1.5 rounded-full bg-emerald-300" /> Private by design</span>
      </header>

      {!result ? <>
        <section className="grid gap-8 pb-8 pt-12 md:grid-cols-[1fr_auto] md:items-end md:pt-16">
          <div><p className="mb-3 text-[11px] font-semibold uppercase tracking-[.22em] text-blue-200/75">Resume · Role · Next step</p>
            <h1 className="max-w-2xl text-4xl font-semibold leading-[1.08] tracking-[-.045em] text-white sm:text-5xl">A sharper resume starts with <span className="text-blue-200">the right role.</span></h1>
            <p className="mt-4 max-w-xl text-sm leading-6 text-zinc-400">See how your experience maps to a real job, which skills matter most, and where to focus next.</p>
          </div>
          <div className="hidden items-center gap-2 pb-1 text-xs text-zinc-500 md:flex"><span className="step-on">01</span> Profile <span className="mx-2 h-px w-8 bg-white/10" /><span className="step-off">02</span> Insights</div>
        </section>

        <form onSubmit={analyze} className="overflow-hidden rounded-2xl border border-white/[.09] bg-[#101114] shadow-[0_28px_90px_-60px_rgba(83,115,182,.3)]">
          <div className="grid md:grid-cols-2">
            <section className="border-b border-white/[.08] p-5 sm:p-7 md:border-b-0 md:border-r">
              <div className="mb-5 flex items-center justify-between"><div><p className="text-[10px] font-bold uppercase tracking-[.2em] text-zinc-500">01 / Your profile</p><h2 className="mt-1 text-lg font-medium text-zinc-100">Resume</h2></div><FileText size={18} className="text-zinc-500" /></div>
              <div onClick={() => inputRef.current?.click()} onDragOver={e => { e.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); chooseFile(e.dataTransfer.files[0]) }} className={`group grid min-h-[230px] cursor-pointer place-items-center rounded-xl border border-dashed p-6 text-center transition ${dragging ? 'border-blue-300 bg-blue-300/[.06]' : 'border-white/[.15] bg-[#0b0c0e] hover:border-blue-200/60 hover:bg-white/[.02]'}`}>
                <input ref={inputRef} className="hidden" type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={e => chooseFile(e.target.files?.[0])} />
                {file ? <div className="max-w-full"><span className="mx-auto grid h-12 w-12 place-items-center rounded-xl border border-emerald-200/20 bg-emerald-200/[.06] text-emerald-200"><Check size={21} /></span><p className="mt-4 max-w-full truncate text-sm font-medium text-zinc-100">{file.name}</p><p className="mt-1 text-xs text-zinc-500">{(file.size / 1024).toFixed(0)} KB · Click to replace</p></div> : <div><span className="mx-auto grid h-12 w-12 place-items-center rounded-xl border border-white/10 bg-white/[.04] text-blue-100"><Upload size={20} /></span><p className="mt-4 text-sm font-medium text-zinc-200">Drop your resume here</p><p className="mt-1 text-xs text-zinc-500">or <span className="text-blue-200">browse files</span></p><p className="mt-4 text-[10px] uppercase tracking-[.14em] text-zinc-600">PDF or DOCX · Up to 5 MB</p></div>}
              </div>
              <div className="mt-4 flex items-start gap-2 text-[11px] leading-5 text-zinc-500"><ShieldAlert size={13} className="mt-0.5 shrink-0" /> File contents are processed in memory and discarded after analysis.</div>
            </section>

            <section className="p-5 sm:p-7">
              <div className="mb-5 flex items-center justify-between"><div><p className="text-[10px] font-bold uppercase tracking-[.2em] text-zinc-500">02 / Target position</p><h2 className="mt-1 text-lg font-medium text-zinc-100">Job description</h2></div><Briefcase size={18} className="text-zinc-500" /></div>
              <textarea value={jd} onChange={e => setJd(e.target.value)} placeholder="Paste the full job description — responsibilities, qualifications, skills, and experience…" className="min-h-[230px] w-full resize-y rounded-xl border border-white/[.1] bg-[#0b0c0e] p-4 text-[13px] leading-6 text-zinc-200 outline-none transition placeholder:text-zinc-600 focus:border-blue-200/50 focus:ring-2 focus:ring-blue-200/[.07]" />
              <div className="mt-2 flex items-center justify-between"><span className="font-mono text-[11px] text-zinc-500"><span className={words >= 80 ? 'text-emerald-200' : 'text-zinc-300'}>{words}</span> / 80 words</span><span className="text-[10px] text-zinc-600">Full posting required</span></div>
              <div className={`mt-3 flex min-h-9 items-start gap-2 rounded-lg px-3 py-2 text-[11px] leading-4 ${validation.valid === true ? 'bg-emerald-300/[.06] text-emerald-200' : validation.valid === false ? 'bg-amber-300/[.05] text-amber-100/80' : 'bg-white/[.025] text-zinc-500'}`}>
                {validation.valid === true ? <CheckCircle2 size={13} className="mt-0.5 shrink-0" /> : validation.valid === false ? <AlertCircle size={13} className="mt-0.5 shrink-0" /> : <LoaderCircle size={13} className="mt-0.5 shrink-0" />}{validation.message}
              </div>
            </section>
          </div>
          <div className="flex flex-col gap-4 border-t border-white/[.08] bg-[#0d0e10] px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-7">
            <label className={`flex items-start gap-2.5 text-[11px] leading-5 ${llmAvailable ? 'cursor-pointer text-zinc-400' : 'text-zinc-600'}`} title={llmAvailable ? '' : 'Add ANTHROPIC_API_KEY to .env to enable Claude.'}>
              <input type="checkbox" checked={useLlm} disabled={!llmAvailable} onChange={e => setUseLlm(e.target.checked)} className="mt-1 accent-blue-300" />
              <span><span className="block text-zinc-300">Claude writing assistance <span className="text-zinc-600">· optional</span></span><span className="text-zinc-600">Shares job text and analysis highlights only. Raw resume file is never sent.</span></span>
            </label>
            <button disabled={!ready} className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-blue-200 px-5 py-3 text-sm font-semibold text-[#10131a] transition hover:bg-blue-100 disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-500 sm:w-auto">{busy ? <><LoaderCircle size={16} className="animate-spin" /> Analyzing</> : <>Analyze my resume <ArrowRight size={16} /></>}</button>
          </div>
        </form>
        {error && <div role="alert" className="mt-4 flex items-start gap-2 rounded-xl border border-rose-300/15 bg-rose-300/[.05] p-4 text-sm text-rose-100"><AlertCircle size={17} className="mt-0.5 shrink-0" />{error}</div>}
        <p className="mx-auto mt-7 max-w-3xl text-center text-[10px] leading-5 text-zinc-600">Your resume is not saved. Job descriptions are checked for readable English, job-related language, and role-specific skills before analysis. Scores are coaching signals, not hiring predictions.</p>
      </> : <Results result={result} recommendations={recommendations} votes={votes} vote={vote} open={open} setOpen={setOpen} reset={reset} />}
    </div>
  </main>
}

function SectionToggle({ title, icon: Icon, open, onClick, meta }) {
  return <button type="button" onClick={onClick} className="flex w-full items-center justify-between gap-3 py-4 text-left"><span className="flex items-center gap-3"><Icon size={16} className="text-blue-200" /><span className="text-sm font-medium text-zinc-200">{title}</span>{meta && <span className="text-[10px] text-zinc-600">{meta}</span>}</span>{open ? <ChevronUp size={16} className="text-zinc-500" /> : <ChevronDown size={16} className="text-zinc-500" />}</button>
}

function Results({ result, recommendations, votes, vote, open, setOpen, reset }) {
  const { skills, parsed_resume: parsed } = result
  const toggle = (key) => setOpen(v => ({ ...v, [key]: !v[key] }))
  const scoreColor = result.score >= 75 ? 'text-emerald-200' : result.score >= 50 ? 'text-blue-200' : 'text-amber-100'
  const links = parsed.contact.links || []
  return <section className="pt-10 sm:pt-14">
    <div className="mb-7 flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
      <div><p className="text-[10px] font-bold uppercase tracking-[.2em] text-blue-200/70">ANALYSIS COMPLETE · {result.recommendation_mode}</p><h1 className="mt-3 text-3xl font-semibold tracking-[-.04em] text-white sm:text-4xl">Your role-fit snapshot</h1><p className="mt-2 text-sm text-zinc-500">{parsed.word_count} resume words · {parsed.pages}</p></div>
      <button onClick={reset} className="inline-flex items-center gap-2 self-start rounded-lg border border-white/10 px-3 py-2 text-xs text-zinc-400 transition hover:border-white/20 hover:text-white sm:self-auto"><RotateCcw size={13} /> New analysis</button>
    </div>

    <div className="grid gap-3 lg:grid-cols-[.78fr_1.4fr]">
      <div className="rounded-2xl border border-white/[.09] bg-[#101114] p-5 sm:p-6">
        <div className="flex items-center justify-between"><span className="text-[10px] font-bold uppercase tracking-[.17em] text-zinc-500">ROLE FIT SCORE</span><Gauge size={17} className="text-blue-200" /></div>
        <div className="mt-6 flex items-end gap-2"><span className={`text-7xl font-semibold leading-none tracking-[-.07em] ${scoreColor}`}>{result.score}</span><span className="pb-2 text-sm text-zinc-600">/ 100</span></div>
        <p className="mt-4 text-sm font-medium text-zinc-200">{result.verdict}</p>
        <p className="mt-2 text-[11px] leading-5 text-zinc-500">Weighted toward required and repeated skills, with evidence from experience and achievements.</p>
        <div className="mt-5 h-px bg-white/[.07]" /><div className="mt-4 flex justify-between text-[10px] text-zinc-600"><span>Evidence-based estimate</span><span>Not an ATS score</span></div>
      </div>

      <div className="rounded-2xl border border-white/[.09] bg-[#101114] px-5 sm:px-6">
        <SectionToggle title="Transparent score breakdown" icon={Gauge} open={open.breakdown} onClick={() => toggle('breakdown')} meta="100 points total" />
        {open.breakdown && <div className="space-y-4 border-t border-white/[.07] pb-5 pt-4">{result.breakdown.map(item => <ScoreBar key={item.name} item={item} />)}</div>}
      </div>
    </div>

    <div className="mt-3 grid gap-3 lg:grid-cols-2">
      <div className="rounded-2xl border border-white/[.09] bg-[#101114] p-5 sm:p-6">
        <div className="mb-4 flex items-center justify-between"><div><p className="text-[10px] font-bold uppercase tracking-[.17em] text-zinc-500">ROLE REQUIREMENTS</p><h2 className="mt-1 text-base font-medium text-zinc-100">Skill priority map</h2></div><ListChecks size={17} className="text-blue-200" /></div>
        {skills.priorities.length ? <div className="max-h-[420px] space-y-2 overflow-auto pr-1">{skills.priorities.map(item => <div key={item.name} className="flex items-center gap-3 rounded-lg border border-white/[.055] bg-white/[.015] px-3 py-2.5"><span className={`h-1.5 w-1.5 rounded-full ${item.priority === 'High' ? 'bg-rose-300' : item.priority === 'Medium' ? 'bg-amber-200' : 'bg-emerald-200'}`} /><span className="min-w-0 flex-1 truncate text-xs text-zinc-200">{item.name}</span><span className={`rounded px-2 py-1 text-[9px] font-semibold uppercase tracking-[.08em] ${priorityClass(item.priority)}`}>{item.priority}</span><span className="hidden min-w-[100px] text-right text-[10px] text-zinc-600 sm:block">{item.matched ? 'Resume evidence found' : item.reason}</span></div>)}</div> : <p className="rounded-lg border border-white/[.06] p-4 text-xs text-zinc-500">No recognized skills were found in this posting.</p>}
        <div className="mt-4 grid grid-cols-3 gap-2 text-center text-[9px] uppercase tracking-[.08em]"><span className="rounded-md border border-rose-200/10 bg-rose-200/[.04] px-2 py-2 text-rose-100/70">High · must-have / repeated</span><span className="rounded-md border border-amber-200/10 bg-amber-200/[.04] px-2 py-2 text-amber-100/70">Medium · relevant</span><span className="rounded-md border border-emerald-200/10 bg-emerald-200/[.04] px-2 py-2 text-emerald-100/70">Low · mentioned</span></div>
      </div>

      <div className="rounded-2xl border border-white/[.09] bg-[#101114] p-5 sm:p-6">
        <div className="mb-4"><p className="text-[10px] font-bold uppercase tracking-[.17em] text-zinc-500">RESUME EVIDENCE</p><h2 className="mt-1 text-base font-medium text-zinc-100">What the match sees</h2></div>
        <SkillChips title="Matched" items={skills.matched} tone="green" empty="No direct skill matches found." />
        <SkillChips title="Missing from resume" items={skills.missing} tone="rose" empty="No recognized skill gaps." />
        <SkillChips title="Other skills detected" items={skills.resume_only} tone="blue" empty="No additional taxonomy skills found." />
      </div>
    </div>

    <section className="mt-3 rounded-2xl border border-white/[.09] bg-[#101114] p-5 sm:p-6">
      <div className="mb-5 flex items-center gap-3"><span className="grid h-9 w-9 place-items-center rounded-lg bg-blue-200/[.07] text-blue-200"><Sparkles size={17} /></span><div><p className="text-[10px] font-bold uppercase tracking-[.17em] text-zinc-500">PERSONALIZED COACHING</p><h2 className="mt-1 text-base font-medium text-zinc-100">Where to focus next</h2></div></div>
      {recommendations.length ? <div className="space-y-2">{recommendations.map((rec, index) => <article key={`${rec.title}-${index}`} className="rounded-xl border border-white/[.07] bg-[#0d0e11] p-4 sm:p-5"><div className="flex items-start gap-3"><span className={`mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-md text-[10px] font-semibold ${priorityClass(rec.priority)}`}>{index + 1}</span><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><span className={`text-[9px] font-bold uppercase tracking-[.12em] ${rec.priority === 'High' ? 'text-rose-200' : rec.priority === 'Medium' ? 'text-amber-100' : 'text-emerald-200'}`}>{rec.priority} priority</span><span className="text-zinc-700">·</span><span className="text-[9px] uppercase tracking-[.12em] text-zinc-500">{rec.category}</span></div><h3 className="mt-2 text-sm font-medium text-zinc-100">{rec.title}</h3><p className="mt-1.5 text-xs leading-5 text-zinc-400">{rec.detail}{rec.job_priority_reason ? ` Job priority: ${rec.job_priority_reason.toLowerCase()}.` : ''}</p>{rec.evidence && <blockquote className="mt-3 border-l border-blue-200/40 pl-3 text-[11px] italic leading-5 text-zinc-500">“{rec.evidence}”</blockquote>}<div className="mt-3 flex items-center gap-2"><span className="mr-1 text-[10px] text-zinc-600">Useful?</span><button onClick={() => vote(rec.category, 'helpful')} className={`rounded-md border px-2 py-1 text-[10px] ${votes[rec.category] === 'helpful' ? 'border-emerald-200/30 text-emerald-100' : 'border-white/10 text-zinc-500 hover:text-zinc-200'}`}>Yes</button><button onClick={() => vote(rec.category, 'not-relevant')} className={`rounded-md border px-2 py-1 text-[10px] ${votes[rec.category] === 'not-relevant' ? 'border-white/20 text-zinc-200' : 'border-white/10 text-zinc-500 hover:text-zinc-200'}`}>Not relevant</button></div></div></div></article>)}</div> : <p className="text-xs text-zinc-500">The resume already covers the main signals found for this role.</p>}
      <p className="mt-4 text-[10px] text-zinc-600">Recommendations come from your resume and this posting. Feedback preferences stay in this browser.</p>
    </section>

    <section className="mt-3 overflow-hidden rounded-2xl border border-white/[.09] bg-[#101114] px-5 sm:px-6">
      <SectionToggle title="Resume sections & contact details" icon={FileText} open={open.details} onClick={() => toggle('details')} meta={`${parsed.sections.filter(s => s.present).length}/${parsed.sections.length} sections detected`} />
      {open.details && <div className="grid gap-5 border-t border-white/[.07] py-5 md:grid-cols-2"><div className="grid grid-cols-2 gap-2">{parsed.sections.map(section => <div key={section.name} className="flex items-center gap-2 rounded-lg border border-white/[.06] px-3 py-2 text-xs"><span className={section.present ? 'text-emerald-200' : 'text-zinc-600'}>{section.present ? <Check size={13} /> : <X size={13} />}</span><span className={section.present ? 'text-zinc-300' : 'text-zinc-600'}>{section.name}</span></div>)}</div><div className="space-y-2 text-xs text-zinc-400">{parsed.contact.name && <p className="flex items-center gap-2"><FileText size={13} className="text-zinc-600" />{parsed.contact.name}</p>}{parsed.contact.email && <p className="flex items-center gap-2"><Mail size={13} className="text-zinc-600" />{parsed.contact.email}</p>}{parsed.contact.phone && <p className="flex items-center gap-2"><Phone size={13} className="text-zinc-600" />{parsed.contact.phone}</p>}{links.map(link => <p key={link} className="flex items-center gap-2 break-all"><a href={`https://${link.replace(/^https?:\/\//, '')}`} target="_blank" rel="noreferrer" className="text-blue-200 hover:underline">{link}</a>{link.toLowerCase().includes('github') ? <Github size={13} /> : <Linkedin size={13} />}</p>)}{!parsed.contact.name && !parsed.contact.email && !parsed.contact.phone && !links.length && <p className="text-zinc-600">No contact details detected.</p>}</div></div>}
    </section>

    <section className="mt-3 overflow-hidden rounded-2xl border border-white/[.09] bg-[#101114] px-5 sm:px-6">
      <SectionToggle title="Job posting safety scan" icon={ShieldAlert} open={open.safety} onClick={() => toggle('safety')} meta={result.job_safety.level} />
      {open.safety && <div className="space-y-3 border-t border-white/[.07] py-5">{result.job_safety.flags?.length ? result.job_safety.flags.map(flag => <div key={flag.label} className="flex gap-3 rounded-lg border border-amber-200/10 bg-amber-200/[.03] p-3"><AlertCircle size={14} className="mt-0.5 shrink-0 text-amber-100" /><div><p className="text-xs font-medium text-zinc-200">{flag.label}</p><p className="mt-1 text-[11px] leading-5 text-zinc-500">{flag.explanation}</p></div></div>) : <p className="text-xs text-zinc-400">No common scam signals detected. This scan does not verify the employer.</p>}<p className="text-[10px] leading-5 text-zinc-600">{result.job_safety.disclaimer}</p></div>}
    </section>

    <section className="mt-3 overflow-hidden rounded-2xl border border-white/[.09] bg-[#101114] px-5 sm:px-6">
      <SectionToggle title="Interview practice" icon={MessageSquareText} open={open.interview} onClick={() => toggle('interview')} meta={`${result.interview_questions.length} prompts`} />
      {open.interview && <div className="space-y-2 border-t border-white/[.07] py-5">{result.interview_questions.map((q, i) => <div key={i} className="rounded-lg border border-white/[.06] bg-white/[.015] p-3"><p className="text-xs font-medium leading-5 text-zinc-200">{q.question}</p><p className="mt-1 text-[10px] text-zinc-600">{q.why}</p></div>)}</div>}
    </section>
    <p className="mt-5 text-center text-[10px] leading-5 text-zinc-600">{result.notice}</p>
    <button onClick={reset} className="mx-auto mt-5 flex items-center gap-2 rounded-lg border border-white/10 px-4 py-2.5 text-xs text-zinc-400 transition hover:border-white/20 hover:text-white"><RotateCcw size={13} /> Analyze another resume</button>
  </section>
}

function ScoreBar({ item }) {
  const amount = item.max ? Math.min(100, item.score / item.max * 100) : 0
  return <div><div className="mb-1.5 flex items-baseline justify-between gap-3"><span className="text-xs font-medium text-zinc-300">{item.name}</span><span className="font-mono text-[10px] text-zinc-400">{item.score} <span className="text-zinc-700">/ {item.max}</span></span></div><div className="h-1 overflow-hidden rounded-full bg-white/[.07]"><div className="h-full rounded-full bg-blue-200 transition-all" style={{ width: `${amount}%` }} /></div><p className="mt-1.5 text-[10px] leading-4 text-zinc-600">{item.explanation}</p></div>
}

function SkillChips({ title, items, tone, empty }) {
  const style = { green: 'border-emerald-200/10 bg-emerald-200/[.04] text-emerald-100/80', rose: 'border-rose-200/10 bg-rose-200/[.04] text-rose-100/80', blue: 'border-blue-200/10 bg-blue-200/[.04] text-blue-100/80' }[tone]
  return <div className="mb-4 last:mb-0"><div className="mb-2 flex items-center justify-between"><span className="text-[10px] uppercase tracking-[.12em] text-zinc-500">{title}</span><span className="font-mono text-[10px] text-zinc-600">{items.length}</span></div>{items.length ? <div className="flex flex-wrap gap-1.5">{items.map(item => <span key={item} className={`rounded-md border px-2 py-1 text-[10px] ${style}`}>{item}</span>)}</div> : <p className="text-[11px] text-zinc-600">{empty}</p>}</div>
}

export default App
