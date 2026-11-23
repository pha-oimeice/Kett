export interface Attachment {
  name: string;
  size: string;
}
export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  attachments?: Attachment[];
  artifact?: boolean;
  liked?: boolean;
  sources?: { title: string; url: string }[];
}
export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  updatedAt: number;
  project?: string;
}

export const suggestions = [
  {
    icon: 'spark',
    title: 'Design a website',
    prompt:
      'Design a minimal coffee brand website that feels warm, natural, and a little unexpected.',
    color: 'peach',
  },
  {
    icon: 'brain',
    title: 'Build a learning plan',
    prompt:
      'Help me build a learning plan I can actually stick to. Break it down and help me find a manageable place to start.',
    color: 'sage',
  },
  {
    icon: 'code',
    title: 'Write a Svelte component',
    prompt:
      'Write a simple Svelte to-do component with support for adding, completing, and deleting tasks. Explain the key implementation details.',
    color: 'lavender',
  },
];

export function seedConversations(): Conversation[] {
  return [
    {
      id: 'welcome-design',
      title: 'A little room to breathe',
      updatedAt: Date.now(),
      messages: [
        {
          id: 's1',
          role: 'user',
          content:
            'I would love a warmer design direction for my personal website.',
        },
        {
          id: 's2',
          role: 'assistant',
          content:
            'Good design does not always need to say more. Sometimes, a little space says enough.\n\nWe could start with three directions:\n\n1. **Natural colors**: warm white, sage green, and a touch of terracotta.\n2. **Room to breathe**: generous spacing that lets your content take the lead.\n3. **Honest details**: a photo you took or a favorite line can feel more personal than elaborate animation.\n\nWhat would you like visitors to discover about you?',
        },
      ],
    },
    {
      id: 'welcome-svelte',
      title: 'Exploring Svelte 5',
      updatedAt: Date.now() - 86400000 * 2,
      messages: [
        { id: 's3', role: 'user', content: 'How do I use $state in Svelte 5?' },
        {
          id: 's4',
          role: 'assistant',
          content:
            '`$state` is the Svelte 5 rune for declaring reactive state. Think of it as a regular variable that automatically keeps your interface in sync.\n\n```svelte\n<script>\n  let count = $state(0);\n</script>\n\n<button onclick={() => count++}>\n  Clicked {count} times\n</button>\n```\n\nNo manual subscriptions or setters are needed. Change `count`, and the interface updates.\n\nFor a value computed from state, use `$derived(count * 2)`.',
        },
      ],
    },
    {
      id: 'welcome-notes',
      title: 'A lighter kind of weekly plan',
      updatedAt: Date.now() - 86400000 * 3,
      messages: [
        {
          id: 's5',
          role: 'user',
          content: 'Help me plan a week that feels a little less overwhelming.',
        },
        {
          id: 's6',
          role: 'assistant',
          content:
            'Let us not fill every space in the calendar. A good plan leaves a little room for life.\n\n- **Monday**: choose just three things that matter most this week.\n- **Tuesday to Thursday**: protect one 90-minute focus session each day.\n- **Friday**: reflect on your progress. Reassess unfinished work instead of automatically carrying it forward.\n- **The weekend**: leave half a day completely unplanned.\n\nTry replacing “How much did I do today?” with “Did I move a little closer to what matters?”',
        },
      ],
    },
  ];
}

export function demoReply(input: string): {
  content: string;
  artifact?: boolean;
} {
  if (
    /代码|组件|编程|程序|待办|\b(code|svelte|component|programming|todo|to-do)\b/i.test(
      input,
    )
  ) {
    return {
      content: `Absolutely. Let us start with a small, complete Svelte 5 component that keeps state and presentation simple.

\`\`\`svelte
<script>
  let input = $state('');
  let tasks = $state([]);

  function addTask() {
    if (!input.trim()) return;
    tasks = [...tasks, {
      id: crypto.randomUUID(),
      text: input.trim(),
      done: false
    }];
    input = '';
  }
</script>

<form onsubmit={(e) => { e.preventDefault(); addTask(); }}>
  <input bind:value={input} placeholder="One small thing…" />
  <button>Add</button>
</form>

{#each tasks as task (task.id)}
  <div>
    <input type="checkbox" bind:checked={task.done} />
    <span style:text-decoration={task.done ? 'line-through' : 'none'}>
      {task.text}
    </span>
    <button onclick={() => tasks = tasks.filter(t => t.id !== task.id)}>
      Delete
    </button>
  </div>
{/each}
\`\`\`

Three details worth noticing:

- **\`$state\`** manages the input and task list, updating the interface automatically.
- **Two-way binding** keeps each checkbox in sync with its task.
- **Stable keys** help Svelte update the right elements when tasks change.

This is preset demo code. Copy it into your Svelte project and make it your own.`,
    };
  }
  if (
    /网站|网页|设计|咖啡|品牌|页面|构建|\b(website|webpage|design|coffee|brand|landing|html)\b/i.test(
      input,
    )
  ) {
    return {
      artifact: true,
      content:
        'I would sum up this direction as: **Slow down. Let good things happen.**\n\nRather than adding more to catch the eye, use space, texture, and a few well-chosen words to make people want to stay.\n\n### The design direction\n\n- **Colors**: oat white, espresso brown, and a little olive green.\n- **Typography**: generous serif headlines with quiet, considered supporting text.\n- **Details**: an illustrated coffee cup, soft corners, and a paper-like warmth.\n\nUse **Download HTML** below to save the sample website.\n\nThis is a built-in frontend demo, not a live AI-generated result. Treat it as a starting point for your own ideas.',
    };
  }
  if (
    /计划|学习|问题|拆解|坚持|效率|工作|规划|\b(plan|planning|learn|learning|study|problem|productivity|work)\b/i.test(
      input,
    )
  ) {
    return {
      content:
        'Of course. We do not need a perfect plan yet. Let us find a starting point you can actually act on.\n\n### 1. Name the change you want\n\nInstead of “I want to get better,” try: **What would I like to be able to do independently a month from now?** A clear outcome makes the next choice easier.\n\n### 2. Make starting feel small\n\nSet aside **20 minutes a day** for one small thing. Not because 20 minutes is enough for everything, but because a rhythm you can keep matters more than an occasional sprint.\n\n### 3. Keep feedback lightweight\n\nSpend 10 minutes each week asking:\n\n- What felt genuinely useful?\n- What friction kept showing up?\n- What could I remove next week, rather than add?\n\n**One step for today**: write down a specific result you care about, and one small thing you can do for it tomorrow.\n\nWhat would you most like to focus on?\n\n> This is a local preset response demonstrating the conversation experience.',
    };
  }
  return {
    content:
      'Got it. Let us move that idea a little further together.\n\nI would start with three questions:\n\n1. **What would you like to achieve?** Describe the result you want to see.\n2. **What do you have already?** Gather your ideas, materials, and constraints.\n3. **What comes next?** Turn the big question into one small action you can take today.\n\nTell me a little more about the context, or explore a creative, planning, or coding direction.\n\n> This is the Kett frontend demo. Responses come from local presets, with no AI service connected. Conversations are saved only in this browser.',
  };
}

export const artifactSource = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Slow Isle · A slower kind of coffee</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f4f1e9;color:#353e30;font-family:Georgia,serif}nav{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:28px 7%;border-bottom:1px solid #35422b20}.logo{font-size:25px;font-weight:bold}nav span:last-child{font:9px system-ui;letter-spacing:1.5px;text-align:right}main{padding:64px 8% 38px;text-align:center}.eyebrow{font:10px system-ui;letter-spacing:4px;color:#7e846d}h1{font-size:clamp(38px,7vw,68px);font-weight:400;line-height:1.3;margin:25px 0}p{font:13px/2 system-ui;color:#858878}.scene{height:225px;position:relative;margin:38px auto 30px;max-width:460px;border-radius:170px 170px 8px 8px;background:#dedfce;overflow:hidden}.sun{width:100px;height:100px;background:#d9b592;border-radius:50%;position:absolute;right:50px;top:24px}.table{position:absolute;bottom:0;width:100%;height:65px;background:#9b9f80}.cup{width:100px;height:85px;border-radius:5px 5px 45px 45px;background:#f9f7ed;position:absolute;bottom:40px;left:calc(50% - 50px);box-shadow:0 12px 14px #3e472126}.cup:before{content:'';position:absolute;width:35px;height:36px;border:10px solid #f9f7ed;border-radius:50%;right:-30px;top:8px}.cup:after{content:'';position:absolute;width:80px;height:13px;border-radius:50%;background:#6a4e36;top:5px;left:10px}.stem{position:absolute;height:110px;width:2px;background:#6a7754;bottom:48px;left:80px;transform:rotate(-18deg)}.stem:before,.stem:after{content:'';position:absolute;width:40px;height:18px;background:#7c8a66;border-radius:0 80% 0 80%;left:-40px;top:20px;transform:rotate(20deg)}.stem:after{left:0;top:50px;transform:rotate(-45deg)}.button{display:inline-block;background:#3d4a35;color:#f7f5ec;padding:14px 24px;border-radius:4px;text-decoration:none;font:12px system-ui;letter-spacing:1px;margin-top:14px}footer{padding:24px 7%;display:flex;justify-content:space-between;gap:15px;font:9px system-ui;color:#949780;border-top:1px solid #35422b20;margin-top:25px}#story{padding:32px 8%;text-align:center}#story h2{font-size:26px;font-weight:400}html{scroll-behavior:smooth}
</style>
</head>
<body>
<nav><span class="logo">slow isle café.</span><span>GOOD COFFEE, SLOW LIVING</span></nav>
<main><div class="eyebrow">A LITTLE PAUSE IN YOUR DAY</div><h1>A slower pace.<br>A better moment.</h1><p>A thoughtfully made coffee. A little time with nowhere to be.<br>Find your own quiet island in the middle of the city.</p><div class="scene"><div class="sun"></div><div class="table"></div><div class="stem"></div><div class="cup"></div></div><a class="button" href="#story">Meet Slow Isle ↗</a></main>
<section id="story"><h2>Good things, thoughtfully brewed.</h2><p>We believe good coffee does not need a complicated reason.<br>Seasonal beans, small-batch roasting, and a little room to discover.</p></section>
<footer><span>© 2026 Slow Isle · Concept design</span><span>MADE WITH A LITTLE PATIENCE</span></footer>
</body>
</html>`;
