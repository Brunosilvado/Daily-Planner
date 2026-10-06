/*
 * ============================================================================
 *  Daily Compass — dashboard logic (runs in the browser, on your phone/laptop)
 * ============================================================================
 *
 * WHAT THIS FILE DOES, IN PLAIN TERMS:
 *   This script turns the plain index.html skeleton into the live dashboard.
 *   It has two kinds of content:
 *
 *   1. STATIC content — the evening-routine schedule and the monthly review
 *      windows. These are just rules written directly into this file (see
 *      `routines` and `plan()` below). They don't depend on any outside
 *      service, so they always work even if every integration is down.
 *
 *   2. LIVE content — calendar events, money figures, and open tasks. These
 *      come from a separate file called data.json, which sits right next to
 *      this one. A robot (a GitHub Action, running on a timer, described in
 *      .github/workflows/deploy.yml) regenerates data.json every few hours
 *      by calling Google Calendar, YNAB and Microsoft To Do. This file just
 *      reads whatever is in data.json at the moment the page loads — it
 *      never calls those services directly itself.
 *
 *   If you're new to reading code: skim the section headers (the big comment
 *   blocks like the one you're reading now) first. Each one is a self-
 *   contained chunk you can understand on its own. The very bottom of the
 *   file is where everything actually kicks off.
 *
 *   A general-purpose helper worth knowing up front: `el(id)` (defined
 *   below) is shorthand for "find the HTML element with this id." It's used
 *   everywhere instead of writing out `document.getElementById(id)` each time.
 */


/* ============================================================================
 *  SECTION 1 — Static evening-routine schedule (no live data involved)
 * ============================================================================
 *  This whole section is self-contained: given a date, `plan(d)` returns
 *  what to do that evening. None of it talks to a network or a file.
 */

// The month is split into five date ranges, each with its own "monthly
// review" focus. Used by the monthly-review banner on the Plan tab, and
// to decide which one is "active right now" based on today's date.
// Each row is: [date range label, title, description, one-step prompt]
const routines=[
  ['1st–3rd','Budget & cash flow','Review accounts, prior spending, card statements and automatic payments. Fund the budget and choose a savings goal after reserves.','Identify one upcoming expense and its budget category.'],
  ['7th–10th','Assets & maintenance','Review cash reserves, vehicle maintenance, insurance renewals and trading-account records.','Check one renewal or maintenance need.'],
  ['14th–17th','Retirement & investments','Review contributions and allocation; learn one investment topic. Reviewing does not require buying or selling.','Verify one planned contribution.'],
  ['20th–23rd','Family planning','Review next month’s calendar, appointments, an outing, a date night, birthdays and meals.','Identify one family date to coordinate.'],
  ['27th–month-end','Monthly wrap-up','Review progress, upcoming expenses and unfinished work. Choose next month’s priorities.','Choose one priority for next month.'],
];

// Given a day-of-month number (1–31), returns which row of `routines`
// (0–4) that day falls into. E.g. the 15th is in the "Retirement &
// investments" window (index 2), since 14 <= 15 < 20.
function windowIndex(day){
  if(day>=27) return 4;
  if(day>=20) return 3;
  if(day>=14) return 2;
  if(day>=7)  return 1;
  return 0;
}

// One-off calendar exceptions where the normal weekly routine should be
// skipped or replaced for a specific date — e.g. a birthday. Keyed by
// "YYYY-MM-DD". Add a new line here only once a real exception is
// confirmed; this is meant to stay a short, hand-curated list, not grow
// into a second calendar.
// Each value has the same shape plan() normally returns: [action title,
// step description, time slot, duration badge, shorter-alternative text,
// "origin" label shown as a small eyebrow tag].
const dateExceptions={
  '2026-10-13':['Keep the evening for Claudia','Your household block is skipped for her birthday.','Protected family evening','No extra task','Rest — no catch-up required.','Calendar exception'],
};

// The heart of the static schedule: given a Date, decide what tonight's
// plan is. Checks, in order: (1) is there a hand-written exception for
// this exact date? (2) otherwise, what day of the week is it — Tuesday,
// Wednesday and Thursday each have their own fixed routine; every other
// day just protects family time with no extra task.
// Returns the same 6-item array shape described in dateExceptions above.
function plan(d){
  const key=d.toISOString().slice(0,10); // "YYYY-MM-DD", used to look up exceptions
  const weekday=d.getUTCDay();           // 0=Sunday, 1=Monday, ... 6=Saturday
  const monthlyWindow=routines[windowIndex(d.getUTCDate())];

  if(dateExceptions[key]) return dateExceptions[key];

  if(weekday===2){ // Tuesday — household monthly-priorities check-in
    return [
      monthlyWindow[1],
      'Choose one step: '+monthlyWindow[2],
      '8:00–8:30 p.m.',
      '30 min max',
      monthlyWindow[3]+' About 5–10 minutes.',
      'Household Routines',
    ];
  }
  if(weekday===3){ // Wednesday — trading study
    return [
      'Study one trading lesson',
      '5 min: choose your next step. 25 min: one lesson or historical example. 5 min: record your takeaway.',
      '8:00–8:35 p.m.',
      '35 min max',
      'Review one historical example and write one takeaway. About 10 minutes.',
      'Trading Development',
    ];
  }
  if(weekday===4){ // Thursday — historical replay & journal
    return [
      'Replay one setup & journal',
      'Use historical replay or simulation. Check the setup against your rules and record one takeaway. No live-trading instruction.',
      '8:00–8:35 p.m.',
      '35 min max',
      'Review one chart against your rules and write one note. About 10 minutes.',
      'Trading Development',
    ];
  }
  // Every other day (Mon/Fri/Sat/Sun): no extra evening task — just
  // protect family time. The headline text varies slightly by day.
  let headline='Keep space for family';
  if(weekday===1) headline='Childcare comes first'; // Monday: Claudia's meeting
  if(weekday===5) headline='An evening together';   // Friday
  return [
    headline,
    'No extra task is scheduled by this routine. Check Calendar for real appointments; leave room for interruptions.',
    'No added evening block',
    'Protected time',
    'Rest. No catch-up session is required.',
    'Standing family priorities',
  ];
}


/* ============================================================================
 *  SECTION 2 — Live data holders
 * ============================================================================
 *  These three variables start out as empty/placeholder shapes so the page
 *  has something sensible to show even before data.json has finished
 *  loading (or if it fails to load at all — see the very bottom of this
 *  file). Once data.json arrives, these get replaced with the real thing.
 *
 *  Keeping the "default shape" here matching exactly what Python's
 *  build_data.py sends (see DEFAULT_LIVE_DATA / DEFAULT_MONEY / DEFAULT_TASKS
 *  there) means the rendering code below never has to special-case
 *  "what if this field is missing" — it's always present, just empty.
 */

let liveData={calendarConnected:false, todoConnected:false, asOf:'', items:{}};
let money={asOf:'', last30:{income:0, spent:0}, thisMonth:{label:'', budgeted:0}, lastMonth:{label:'', income:0, spent:0}, expectedMonthlyIncome:0, overBudgetCategories:[], note:''};
let tasks={asOf:'', groups:[]};
let generatedAt=null; // when data.json was last regenerated, filled in once it loads


/* ============================================================================
 *  SECTION 3 — Small shared helpers
 * ============================================================================
 */

// Formats a number as US currency, e.g. money$(-42.5) -> "-$42.50".
// Used everywhere a dollar figure is displayed so formatting stays
// consistent (always 2 decimal places, always a leading $ or -$).
function money$(n){
  const sign = n<0 ? '-$' : '$';
  const amount = Math.abs(n).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
  return sign+amount;
}

// Shorthand used throughout this file: el('date') instead of writing
// document.getElementById('date') every time.
const el=id=>document.getElementById(id);

// Which TOP-LEVEL tab is currently selected: 'plan' | 'money'. Changed by
// the top nav's click handler near the bottom of this file.
let view='plan';

// Within the Plan tab, which DAY is currently selected: 'today' |
// 'tomorrow'. This used to be what `view` itself tracked (back when Today
// and Tomorrow were their own separate top-level tabs) — now it's a
// smaller, independent toggle living inside the Plan tab. Changed by the
// day-toggle's click handler near the bottom of this file.
let day='today';

// Returns "today" as a Date object, anchored to the Central time zone
// (America/Chicago) regardless of what time zone the viewer's own device
// is set to — so Bruno and Claudia always see the same "today" even if
// one phone has a different time zone configured.
//
// How: ask Intl for today's Y/M/D *as seen in Central time*, then build a
// brand-new Date from those numbers at a fixed UTC noon. Anchoring at
// noon UTC (rather than midnight) sidesteps a subtle bug: midnight UTC on
// a given date is actually still "yesterday evening" in Central time, so
// any later code that reads this Date back out in UTC (which this file
// does throughout, via getUTCDay()/getUTCDate()/etc.) could silently see
// the wrong day. Noon UTC is never close enough to a date boundary in any
// real-world time zone for that to happen.
function today(){
  const parts=new Intl.DateTimeFormat('en-US',{timeZone:'America/Chicago',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
  const p=Object.fromEntries(parts.map(x=>[x.type,x.value]));
  return new Date(`${p.year}-${p.month}-${p.day}T12:00:00Z`);
}


/* ============================================================================
 *  SECTION 4 — Money tab rendering
 * ============================================================================
 *  Builds the whole Money tab's content from the `money` object (filled in
 *  from data.json — see fetch_ynab.py for where those numbers come from).
 *  Called on every render(), regardless of which tab is actually visible,
 *  because it's cheap and keeps the Money tab's content current even while
 *  you're looking at a different tab.
 */
function renderMoney(){
  const last30Net = money.last30.income - money.last30.spent;
  const lastNet = money.lastMonth.income - money.lastMonth.spent;
  // "Do we have any real YNAB data yet?" — true once at least one of
  // these numbers is non-zero. Used to tell "connected but genuinely
  // $0 everywhere" apart from "not connected, so everything defaults to 0".
  const hasData = !!(money.last30.income || money.last30.spent || money.thisMonth.budgeted);
  const budgeted = money.thisMonth.budgeted || 0;
  const expected = money.expectedMonthlyIncome || 0;
  const overBudgeted = hasData && expected>0 && budgeted>expected;
  // Default to [] here too (not just in Section 2's initial `money`
  // value) so a stale cached data.json from before this field existed
  // can't crash this function on a slow-to-refresh device.
  const overCategories = money.overBudgetCategories || [];

  // Signal dot: green while the last 30 days of real cash flow is positive,
  // this month's budgeted amount hasn't outrun expected income, AND no
  // individual category has overspent; amber the moment any of those
  // tips the wrong way; idle/grey if there's nothing yet.
  el('moneyDot').className = 'dot' + (!hasData ? '' : (last30Net<0||overBudgeted||overCategories.length ? ' warn' : ' ok'));

  // Small local helper: turns a list of [label, value, cssClass] triples
  // into a <div> full of label/value rows, matching the .stat-row style
  // in style.css. Used for both the main body and the "last month" panel.
  const buildRows=(entries)=>{
    const wrap=document.createElement('div');
    entries.forEach(([label,val,cls])=>{
      const row=document.createElement('div');
      row.className='stat-row'+(cls?' '+cls:'');
      const labelEl=document.createElement('span'); labelEl.textContent=label;
      const valueEl=document.createElement('b'); valueEl.textContent=val;
      row.append(labelEl,valueEl);
      wrap.appendChild(row);
    });
    return wrap;
  };

  const bodyWrap=document.createElement('div');

  if(!hasData){
    const empty=document.createElement('p');
    empty.className='sub'; empty.style.margin='0';
    empty.textContent='No YNAB activity yet.';
    bodyWrap.appendChild(empty);
  } else {
    // Headline: the one number that answers "am I saving money right now?"
    // Last 30 days, not calendar month — see fetch_ynab.py for why: a
    // calendar month resets to $0 on the 1st, so a credit-card payment
    // covering last month's purchases would otherwise make a brand-new
    // month look artificially bad for the first few days.
    const headline=document.createElement('div'); headline.className='money-headline';
    const hLabel=document.createElement('span'); hLabel.className='label';
    hLabel.textContent='Net · last 30 days';
    const hValue=document.createElement('span'); hValue.className='value'+(last30Net<0?' warn':'');
    hValue.textContent=(last30Net>=0?'+':'')+money$(last30Net);
    headline.append(hLabel,hValue);
    bodyWrap.appendChild(headline);

    bodyWrap.appendChild(buildRows([
      ['Received', money$(money.last30.income), ''],
      ['Spent', money$(money.last30.spent), ''],
    ]));

    // The budget-vs-expected-income bar — only shown once an expected
    // income figure is actually configured (YNAB_EXPECTED_MONTHLY_INCOME
    // in the GitHub repo's Actions "Variables").
    if(expected>0){
      const barWrap=document.createElement('div'); barWrap.className='budget-bar-wrap';
      const labels=document.createElement('div'); labels.className='budget-bar-labels';
      const left=document.createElement('span'); left.textContent=`${money.thisMonth.label} budgeted `+money$(budgeted);
      const right=document.createElement('span'); right.textContent='Expected income '+money$(expected);
      labels.append(left,right);
      const bar=document.createElement('div'); bar.className='budget-bar';
      const fill=document.createElement('div'); fill.className='budget-bar-fill'+(overBudgeted?' warn':'');
      // Clamp to 0–100% so a wildly over-budget month doesn't blow the bar
      // past the edge of its container.
      const pct=Math.max(0,Math.min(100,(budgeted/expected)*100));
      fill.style.width=pct+'%';
      bar.appendChild(fill);
      barWrap.append(labels,bar);
      bodyWrap.appendChild(barWrap);
    }

    // Per-category overspending alert — this is the "which category"
    // detail the overall budget bar above can't show, since a month can
    // be comfortably under its total budget while one specific category
    // (groceries, say) has still run over. Only appears once there's
    // actually something to flag.
    if(overCategories.length){
      const alertWrap=document.createElement('div'); alertWrap.className='over-budget-alert';
      const heading=document.createElement('b'); heading.style.color='var(--warn)';
      heading.textContent='Over budget this month:';
      alertWrap.appendChild(heading);
      const ul=document.createElement('ul');
      ul.style.margin='4px 0 0'; ul.style.paddingLeft='18px'; ul.style.fontSize='.88rem';
      overCategories.forEach(c=>{
        const li=document.createElement('li');
        // textContent, not innerHTML: c.category is a real YNAB category
        // name you typed yourself, but it's still outside data this file
        // controls — same discipline as calendar/task text elsewhere, so
        // a category literally named with HTML in it still can't do
        // anything to the page.
        li.textContent=c.category+' — '+money$(c.over)+' over';
        ul.appendChild(li);
      });
      alertWrap.appendChild(ul);
      bodyWrap.appendChild(alertWrap);
    }

    // One plain-English sentence summarizing the overall state. The
    // per-category alert above already covers "which category," so this
    // sentence sticks to the two whole-month signals (cash flow,
    // budgeted-vs-expected) and just adds a short nudge toward the alert
    // list when a category is over too, rather than repeating it.
    let statusLine='';
    if(last30Net<0 && overBudgeted) statusLine='Spending has passed income over the last 30 days, and this month’s budgeted more than you expect to earn.';
    else if(last30Net<0) statusLine='Spending has passed income over the last 30 days.';
    else if(overBudgeted) statusLine='This month’s budgeted more than the expected income.';
    else statusLine='Income is covering spending, and this month’s budget is within expected income.';
    if(overCategories.length) statusLine+=' See the over-budget categories above.';
    const status=document.createElement('p');
    status.className='sub'; status.style.margin='12px 0 0'; status.style.fontWeight='600';
    status.style.color=(last30Net<0||overBudgeted||overCategories.length)?'var(--warn)':'var(--ink-soft)';
    status.textContent=statusLine;
    bodyWrap.appendChild(status);
  }

  // Footer note — whatever caveat fetch_ynab.py sent (e.g. "card
  // purchases that don't auto-sync may understate spending"), plus a
  // "Synced <time>" stamp once we actually have a timestamp.
  const note=document.createElement('p');
  note.className='sub'; note.style.margin='10px 0 0';
  note.textContent=money.note+(money.asOf?' Synced '+money.asOf+'.':'');
  bodyWrap.appendChild(note);

  el('moneyBody').replaceChildren(bodyWrap);

  // The collapsed "Last month (for reference)" panel — same three-row
  // shape (received/spent/net) but for the prior calendar month.
  const lastRows=[
    [`${money.lastMonth.label} — received`, money$(money.lastMonth.income), ''],
    [`${money.lastMonth.label} — spent`, money$(money.lastMonth.spent), ''],
    [`${money.lastMonth.label} — net`, (lastNet>=0?'+':'')+money$(lastNet), lastNet<0?'warn':'good'],
  ];
  el('moneyLastMonth').replaceChildren(buildRows(lastRows));
}


/* ============================================================================
 *  SECTION 4.5 — computeTopPriority(): the "Do This First" decision
 * ============================================================================
 *  The single most important function added in the October 2026 redesign.
 *  Instead of making you scan five different cards to figure out what
 *  actually needs doing, this picks ONE thing and hands it to render()
 *  to show as the very first thing on the page.
 *
 *  It checks, in order (first match wins — this IS the priority order):
 *    1. A task that's BOTH overdue AND flagged "!!" — the worst combination.
 *    2. Any overdue task (even unflagged — a missed deadline outranks
 *       everything except #1).
 *    3. Any task you've flagged "!!" as a priority, whatever its due date.
 *    4. A task due exactly on the day you're viewing (today/tomorrow).
 *    5. A calendar event flagged "!!" for the day you're viewing.
 *    6. Nothing more urgent found — fall back to tonight's standing
 *       routine (the same plan() logic the card below it also shows).
 *
 *  Returns {tag, title, detail} — three short strings, nothing more. It
 *  deliberately does NOT remove its pick from the lists shown further
 *  down the page (Due Today, Calendar, Tasks) — seeing the same item
 *  again there is fine; this card's job is just to say "start here."
 */
function computeTopPriority(dayKey, p){
  const fallback={tag:'Tonight’s standing routine', title:p[0], detail:p[1]};
  if(!liveData.todoConnected) return fallback;

  // Flatten every To Do list into one array, same pattern as the Due
  // Today card below — keeping which list each item came from, since
  // that's useful context in the detail line.
  const flat=[];
  tasks.groups.forEach(g=>g.items.forEach(it=>flat.push({...it, list:g.list})));

  const overdueFlagged=flat.find(it=>it.overdue && it.priority);
  if(overdueFlagged) return {
    tag:'Overdue & flagged',
    title:overdueFlagged.text,
    detail:overdueFlagged.list+(overdueFlagged.due?' · was due '+overdueFlagged.due:''),
  };

  const overdue=flat.find(it=>it.overdue);
  if(overdue) return {
    tag:'Overdue',
    title:overdue.text,
    detail:overdue.list+(overdue.due?' · was due '+overdue.due:''),
  };

  const flagged=flat.find(it=>it.priority);
  if(flagged) return {
    tag:'Flagged priority',
    title:flagged.text,
    detail:flagged.list+(flagged.due?' · due '+flagged.due:' · no due date'),
  };

  const dueNow=flat.find(it=>it.dueISO===dayKey);
  if(dueNow) return {
    tag: day==='tomorrow' ? 'Due tomorrow' : 'Due today',
    title:dueNow.text,
    detail:dueNow.list,
  };

  const dayEvents=liveData.items[dayKey]||[];
  const flaggedEvent=dayEvents.find(it=>it.priority);
  if(flaggedEvent) return {
    tag:'Flagged on your calendar',
    title:flaggedEvent.text,
    detail:flaggedEvent.time||'All day',
  };

  return fallback;
}


/* ============================================================================
 *  SECTION 5 — Main render: builds whichever tab is currently selected
 * ============================================================================
 *  This is the biggest function in the file, because it's responsible for
 *  both top-level tabs (Plan, Money) and, within Plan, both days (Today,
 *  Tomorrow) and the monthly-review banner. It's called once when the page
 *  first loads data.json, and again every time someone taps the top nav or
 *  the Today/Tomorrow toggle (see the click-handlers near the bottom of
 *  this file).
 *
 *  A quick map of what happens, in order:
 *    1. Figure out which top-level tab is active, show/hide containers.
 *    2. Always refresh the Money tab's content (cheap, keeps it current).
 *    3. If the Money tab is the active one, finish early — it doesn't need
 *       any of the Plan-tab content below.
 *    4. Compute and fill in "Do This First" (computeTopPriority() above).
 *    5. Fill in the monthly-review banner (just the active window; the
 *       full five-window list lives behind its own <details> disclosure).
 *    6. Fill in the standing evening-routine card (the static `plan()`
 *       logic) and the "Protect your time" timeline.
 *    7. Set the top-right status pill to whichever data source is actually
 *       relevant for the active tab.
 *    8. Fill in the "Due today/tomorrow" card.
 *    9. Fill in the "Beyond your standing schedule" card (Calendar events).
 *   10. Fill in the full "Open tasks" section (every open To Do item).
 */
function render(){
  const moneyView = view==='money';

  // Show/hide the two top-level containers to match the active tab.
  el('planView').hidden=moneyView;
  el('money').hidden=!moneyView;
  // Keep the top nav buttons' pressed/unpressed state (and thus their
  // highlighting) in sync with the active tab, for accessibility as much
  // as styling — aria-pressed is what a screen reader announces. Same
  // pattern for the Today/Tomorrow toggle just below.
  document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',String(view===b.dataset.view)));
  document.querySelectorAll('[data-day]').forEach(b=>b.setAttribute('aria-pressed',String(day===b.dataset.day)));

  renderMoney(); // independent of which tab is showing; cheap, keeps state current if viewer switches

  // The top-right pill always reflects whichever data source the current
  // tab actually depends on — Calendar on Plan, YNAB on Money — rather
  // than always showing Calendar status regardless of what's on screen.
  if(moneyView){
    const moneyHasData=!!(money.last30.income||money.last30.spent||money.thisMonth.budgeted);
    el('connStatus').textContent = moneyHasData ? 'YNAB live · '+money.asOf : 'Not connected';
    el('connStatus').className = moneyHasData ? 'pill live' : 'pill';
    return; // Money tab is fully handled by renderMoney() above — nothing more to do
  }

  // ---- Everything below this line is the Plan tab ----

  // `d` is whichever day the toggle has selected, as an actual Date; a
  // SEPARATE `realToday` always stays the actual current date, because
  // the monthly-review banner further down is about where we are in the
  // calendar month right now, not which day you happen to be previewing.
  const d=today();
  if(day==='tomorrow') d.setUTCDate(d.getUTCDate()+1); // shift "today" forward one day
  const realToday=today();

  el('date').textContent = new Intl.DateTimeFormat('en-US', {
    timeZone:'UTC', weekday:'long', month:'short', day:'numeric',
  }).format(d);
  el('label').textContent = day.toUpperCase()+' · CENTRAL TIME';

  // Fill in the big "tonight's focus" card from the static plan() logic.
  const p=plan(d);
  el('action').textContent=p[0];
  el('step').textContent=p[1];
  el('slot').textContent=p[2];
  el('duration').textContent=p[3];
  el('alternative').textContent=p[4];
  el('origin').textContent=p[5];

  // "YYYY-MM-DD" for whichever day is on screen — used both to look up
  // today's/tomorrow's calendar events (liveData.items is keyed by this)
  // and to match To Do items whose due date equals this day. Computed
  // here (before the "Do This First" card below) because
  // computeTopPriority() needs it too.
  const key=d.toISOString().slice(0,10);

  // ---- "Do This First" — see computeTopPriority() above for the logic ----
  const topPriority=computeTopPriority(key,p);
  el('topPriorityTag').textContent=topPriority.tag;
  el('topPriorityTitle').textContent=topPriority.title;
  el('topPriorityDetail').textContent=topPriority.detail;

  // ---- Monthly-review banner (replaces the old standalone Monthly tab) ----
  // Deliberately keyed off `realToday`, not `d` — which review window is
  // "active" is a fact about today's real date, and shouldn't change just
  // because you tapped over to preview Tomorrow.
  const activeWindowIndex=windowIndex(realToday.getUTCDate());
  const activeWindow=routines[activeWindowIndex];
  el('monthlyBannerLabel').textContent=`This period (${activeWindow[0]}): ${activeWindow[1]}`;
  el('monthlyBannerStep').textContent=activeWindow[3];
  // The full five-window list, inside the "See all review windows"
  // disclosure — same markup as the old Monthly tab used, just living in
  // a <details> instead of its own tab.
  el('windows').replaceChildren(...routines.map((r,i)=>{
    const article=document.createElement('article');
    article.className='window'+(i===activeWindowIndex?' active':'');
    const dateLabel=document.createElement('b');
    const body=document.createElement('div');
    const title=document.createElement('h4');
    const desc=document.createElement('p');
    dateLabel.textContent=r[0]; title.textContent=r[1]; desc.textContent=r[2];
    body.append(title,desc);
    article.append(dateLabel,body);
    return article;
  }));

  // The "Full day schedule" timeline — a fixed weekday-vs-weekend
  // schedule, with tonight's evening-routine action (p[0]) slotted into
  // the 8 p.m. row on weekdays. Lives behind a <details> now (see
  // index.html) since "Do This First" and the standing-routine card
  // above already say what to do — this is for when you want the whole
  // day laid out.
  const weekday=d.getUTCDay();
  const rows = (weekday>0 && weekday<6)
    ? [['7–3:30','Work + 45-min commute each way'],['4:30–7:45','Baby care, dinner & shower'],['8 p.m.',p[0]],['9 p.m.','Time with Claudia'],['9:30 p.m.','Bed']]
    : [['Morning',weekday===0?'Church':'Family / park'],['Afternoon','Family / flexible time'],['9 p.m.','Time with Claudia'],['9:30 p.m.','Bed']];
  el('timeline').replaceChildren(...rows.map(([t,s])=>{
    const li=document.createElement('li'), time=document.createElement('time'), span=document.createElement('span');
    time.textContent=t; span.textContent=s;
    li.append(time,span);
    return li;
  }));

  // Status pill reflects whether Google Calendar is actually connected —
  // the only live source the Plan tab's cards depend on directly (the
  // standing routine and monthly banner above are static, no live source).
  if(liveData.calendarConnected){
    el('connStatus').textContent='Calendar live · '+liveData.asOf;
    el('connStatus').className='pill live';
  } else {
    el('connStatus').textContent='Not connected';
    el('connStatus').className='pill';
  }

  const items=liveData.items[key];
  // Small reusable snippet appended to the Calendar card whenever To Do
  // isn't connected, so that fact surfaces in context rather than only on
  // the (collapsed) Tasks card.
  const todoNote = liveData.todoConnected ? '' :
    `<div class="howto" style="margin-top:10px">Microsoft To&nbsp;Do isn't connected yet, so task highlights aren't shown here.</div>`;

  // ---- "Due today" card ----
  // The whole point is that these can't get missed, so they get their own
  // always-visible card near the top of the page instead of living only
  // inside the collapsed "Open tasks" section further down. Scoped to
  // whichever day is on screen (today or tomorrow), PLUS anything already
  // overdue (relevant no matter which day you're looking at, since by
  // definition it needed attention before now), PLUS anything you've
  // flagged "!!" as a priority (see fetch_todo.py) — a flagged item
  // belongs here regardless of its due date, since marking it that way
  // IS the point: it's important enough that you don't want to have to
  // go looking for it in the full task list below.
  {
    const dueCard=el('dueTodayCard');
    if(!liveData.todoConnected){
      // Nothing to show yet — the full "Open tasks" section below already
      // explains the not-connected state, so this card just stays hidden
      // rather than repeating that message a second time.
      dueCard.hidden=true;
    } else {
      // Flatten every group's items into one list, keeping only the ones
      // that are overdue (any date), due exactly on `key`, or flagged.
      const dueItems=[];
      tasks.groups.forEach(g=>{
        g.items.forEach(it=>{
          if(it.overdue || it.dueISO===key || it.priority) dueItems.push({...it, list:g.list});
        });
      });
      // Most-urgent-first: overdue beats everything, then a priority
      // flag, then keep whatever order they arrived in otherwise. Both
      // comparisons are the same "false sorts before true" trick: when
      // a and b tie on overdue, the tie is broken by priority; when they
      // tie on both, 0 leaves their relative order alone.
      dueItems.sort((a,b)=>(a.overdue!==b.overdue) ? (a.overdue?-1:1) : (a.priority!==b.priority) ? (a.priority?-1:1) : 0);

      dueCard.hidden=false;
      el('dueTodayTitle').textContent = day==='tomorrow' ? 'Due tomorrow' : 'Due today';
      el('dueTodayDot').className = dueItems.some(it=>it.overdue) ? 'dot warn' : 'dot ok';

      if(!dueItems.length){
        el('dueTodayBody').innerHTML =
          '<p style="margin:0;font-size:.88rem">Nothing due '+(day==='tomorrow'?'tomorrow':'today')+' — you\'re clear.</p>';
      } else {
        const list=document.createElement('ul');
        list.style.margin='0'; list.style.paddingLeft='18px'; list.style.fontSize='.88rem';
        dueItems.forEach(it=>{
          const li=document.createElement('li'); li.style.marginBottom='4px';
          // Both classes can apply at once (an overdue, flagged item is
          // both red AND bold) — see .overdue/.priority in style.css.
          li.className=[it.overdue?'overdue':'',it.priority?'priority':''].filter(Boolean).join(' ');
          // Was this pulled in only because it's flagged, with no due
          // date today/tomorrow and not overdue? Say so explicitly,
          // since otherwise a flagged-but-not-due item showing up here
          // with no due-date text at all would look unexplained.
          const onlyBecauseFlagged = it.priority && !it.overdue && it.dueISO!==key;
          // textContent, not innerHTML: it.text and it.list come from
          // Microsoft To Do, so they're treated as plain text, never
          // markup, the same way the full task list below does it. This
          // matters even though we trust the data source: it means a task
          // or list NAMED something that looks like HTML can never change
          // how the page itself behaves.
          li.textContent=(it.priority?'★ ':'')+it.text+' — '+it.list
            +(it.overdue?' (overdue)':onlyBecauseFlagged?' (flagged priority)':'');
          list.appendChild(li);
        });
        el('dueTodayBody').replaceChildren(list);
      }
    }
  }

  // ---- "Beyond your standing schedule" card (Google Calendar events) ----
  {
    if(!liveData.calendarConnected){
      el('calDot').className='dot';
      el('liveBody').innerHTML=`<p style="margin:0;font-size:.88rem">Google Calendar isn't connected to this dashboard yet, so no live appointments are shown here — showing a made-up agenda would be worse than showing none.</p>
        <div class="howto">Waiting on the scheduled refresh to connect it.</div>${todoNote}`;
    } else if(items === undefined){
      // Connected, but liveData.items has no entry at all for this exact
      // date — meaning the last refresh didn't cover it (e.g. the data
      // is more than a day stale). Different from "checked, found
      // nothing" below.
      el('calDot').className='dot warn';
      el('liveBody').innerHTML=`<p style="margin:0;font-size:.88rem">Calendar is connected, but this date hasn't been checked yet.</p>${todoNote}`;
    } else if(items.length===0){
      el('calDot').className='dot ok';
      el('liveBody').innerHTML=`<p style="margin:0;font-size:.88rem">Checked — nothing beyond your standing schedule.</p>${todoNote}`;
    } else {
      el('calDot').className='dot ok';
      const list=document.createElement('ul');
      list.style.margin='0'; list.style.paddingLeft='18px'; list.style.fontSize='.88rem';
      items.forEach(it=>{
        const li=document.createElement('li'); li.style.marginBottom='4px';
        // it.priority: a "!!"-flagged event (see fetch_calendar.py) —
        // already sorted to the front of today's/tomorrow's list by
        // that same file, this just adds the visual marker here.
        if(it.priority) li.className='priority';
        li.textContent=(it.priority?'★ ':'')+(it.time?it.time+' — ':'')+it.text; // textContent: see the note above about why
        list.appendChild(li);
      });
      el('liveBody').replaceChildren(list);
      if(todoNote) el('liveBody').insertAdjacentHTML('beforeend', todoNote);
    }
  }

  // ---- Full "Open tasks (To Do)" section — every open item, grouped by list ----
  {
    // Distinguish "not connected yet" from "connected, and genuinely
    // nothing open" so an empty list doesn't quietly read as a working
    // connection when it might not be one.
    if(!liveData.todoConnected){
      el('taskDot').className='dot';
      el('taskBody').innerHTML='<p style="margin:0;font-size:.88rem">Microsoft To&nbsp;Do isn\'t connected to this dashboard yet, so no tasks are shown here.</p>';
    } else if(!tasks.groups.length){
      el('taskDot').className='dot ok';
      el('taskBody').innerHTML='<p style="margin:0;font-size:.88rem">Checked — no open tasks outside your routines.</p>'+(tasks.asOf?`<p class="sub" style="margin:4px 0 0">Synced ${tasks.asOf}.</p>`:'');
    } else {
      // Warn dot if ANY item in ANY group is overdue, otherwise ok.
      el('taskDot').className = tasks.groups.some(g=>g.items.some(i=>i.overdue)) ? 'dot warn' : 'dot ok';
      const wrap=document.createElement('div');
      tasks.groups.forEach(g=>{
        const div=document.createElement('div'); div.className='taskgroup';
        const heading=document.createElement('b'); heading.textContent=g.list;
        const ul=document.createElement('ul');
        // Already sorted overdue-then-flagged-then-rest by fetch_todo.py
        // — this loop just renders that order with the right visual marks.
        g.items.forEach(it=>{
          const li=document.createElement('li');
          li.className=[it.overdue?'overdue':'',it.priority?'priority':''].filter(Boolean).join(' ');
          li.textContent=(it.priority?'★ ':'')+it.text+(it.due?' (due '+it.due+')':'')+(it.overdue?' — overdue':'');
          ul.appendChild(li);
        });
        div.append(heading,ul);
        wrap.appendChild(div);
      });
      const note=document.createElement('p');
      note.className='sub'; note.style.margin='4px 0 0';
      note.textContent='Routine checklists (Household Routines, Trading Development) not shown here.'+(tasks.asOf?' Synced '+tasks.asOf+'.':'');
      el('taskBody').replaceChildren(wrap, note);
    }
  }
}


/* ============================================================================
 *  SECTION 6 — Wiring: nav buttons, footer, and the initial data.json load
 * ============================================================================
 */

// The top nav (Plan/Money) carries its target tab name in a
// data-view="..." attribute (see index.html). Clicking one just updates
// the `view` variable and re-renders — no page navigation happens.
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>{
  view=b.dataset.view;
  render();
}));

// The Today/Tomorrow toggle inside the Plan tab works the same way, just
// with its own `day` variable and data-day="..." attribute.
document.querySelectorAll('[data-day]').forEach(b=>b.addEventListener('click',()=>{
  day=b.dataset.day;
  render();
}));

// Footer text: "Data refreshed <when> by a scheduled GitHub Action." Shows
// "unknown" if data.json never loaded at all (generatedAt stays null).
function renderFooter(){
  const generatedLabel = generatedAt
    ? new Intl.DateTimeFormat('en-US',{timeZone:'America/Chicago',dateStyle:'medium',timeStyle:'short'}).format(new Date(generatedAt))+' Central'
    : 'unknown';
  el('footer').textContent = 'Data refreshed '+generatedLabel+' by a scheduled GitHub Action. Weekly rhythm and monthly windows are standing rules and stay accurate on their own.';
}

// The one network request this whole page makes: fetch the pre-built
// data.json that sits next to this file (same folder, same deploy — not a
// live call to Google/YNAB/Microsoft, which only the GitHub Action does).
// {cache:'no-store'} tells the browser never to reuse a cached copy, so a
// phone that was last open hours ago always asks for the freshest version
// the instant this page is opened again. (A *stale copy of this script
// itself*, app.js, is a separate caching problem — see build_site.py's
// cache-busting comment for how that's handled.)
fetch('./data.json', {cache:'no-store'})
  .then(r=>r.ok ? r.json() : Promise.reject(r.status))
  .then(d=>{
    generatedAt=d.generatedAt||null;
    if(d.liveData) liveData=d.liveData;
    if(d.money) money=d.money;
    if(d.tasks) tasks=d.tasks;
  })
  .catch(()=>{
    // Something went wrong fetching or parsing data.json (offline, a bad
    // deploy, whatever). Deliberately do nothing here except let the
    // placeholder defaults from Section 2 stand — render() below still
    // shows an honest "not connected" dashboard rather than a blank page
    // or a cryptic error.
  })
  .finally(()=>{
    // Runs whether the fetch above succeeded or failed — there's always
    // something sensible to render, even if it's all defaults.
    render();
    renderFooter();
  });
