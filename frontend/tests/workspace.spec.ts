import { readFile } from 'node:fs/promises';
import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  // Keep tests on preset replies even when the backend and Ollama are running.
  await page.route('**/api/models', (route) => route.abort());
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
});

test('new conversation has no suggested prompts and keeps the keyboard composer', async ({
  page,
}) => {
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page).toHaveTitle('Kett');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(
    'New conversation',
  );
  await expect(page.getByRole('button', { name: 'Kett home' })).toHaveText(
    /😅/,
  );
  await expect(page.getByText('Only you', { exact: true })).toHaveCount(0);
  await expect(
    page.getByRole('button', { name: 'Workbench', exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole('button', { name: 'Chat', exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole('button', { name: 'Send message', exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole('heading', { name: 'Suggested prompts' }),
  ).toHaveCount(0);
  const composer = page.getByRole('textbox', { name: 'Message Kett' });
  await expect(composer).toHaveValue('');
  await composer.fill('Hello');
  const modelButton = page.getByRole('button', { name: 'Select model' });
  const modelMenu = page.locator('.model-menu');
  await modelButton.click();
  await expect(modelButton).toHaveAttribute('aria-expanded', 'true');
  await expect(modelMenu).toContainText('No models available');
  await expect(
    modelMenu.getByRole('button', { name: 'Add model' }),
  ).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(modelButton).toHaveAttribute('aria-expanded', 'false');
  await modelButton.click();
  await page.getByRole('textbox', { name: 'Message Kett' }).click();
  await expect(modelMenu).toHaveCount(0);
  await page
    .getByRole('textbox', { name: 'Message Kett' })
    .press('Shift+Enter');
  await expect(page.locator('.messages')).toHaveCount(0);
  await page.screenshot({ path: 'test-results/welcome-desktop.png' });
});

test('the add button discovers and selects a model from the configured server', async ({
  page,
}) => {
  let requests = 0;
  await page.route('**/api/models', async (route) => {
    requests += 1;
    const response =
      requests === 1 ? ['existing:latest'] : ['existing:latest', 'new:latest'];
    await route.fulfill({ json: response });
  });
  await page.reload();
  const selector = page.getByRole('button', { name: 'Select model' });
  await selector.click();
  const menu = page.locator('.model-menu');
  await expect(
    menu.getByRole('button', { name: 'existing:latest' }),
  ).toBeVisible();
  await menu.getByRole('button', { name: 'Add model' }).click();
  const dialog = page.getByRole('dialog', { name: 'Add model' });
  await expect(dialog).toContainText('configured Ollama server');
  await expect(dialog.getByRole('textbox')).toHaveCount(0);
  await expect(
    dialog.getByRole('button', { name: 'Add existing:latest' }),
  ).toHaveCount(0);
  await dialog.getByRole('button', { name: 'Add new:latest' }).click();
  const selected = page.getByRole('button', { name: 'new:latest' });
  await expect(selected).toBeFocused();
  await selected.click();
  await expect(
    menu.getByRole('button', { name: 'new:latest' }),
  ).toHaveAttribute('aria-pressed', 'true');
  await menu.getByRole('button', { name: 'Add model' }).click();
  await expect(dialog.getByRole('status')).toHaveText(
    'No new models found on the configured server.',
  );
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(selected).toBeFocused();
});

test('streams a local response and persists history across reloads', async ({
  page,
}) => {
  const input = page.getByRole('textbox', { name: 'Message Kett' });
  await input.fill('Hello, a new idea');
  await input.press('Enter');
  await expect(
    page.getByRole('button', { name: 'Stop generating' }),
  ).toBeVisible();
  await expect(page.locator('.assistant .markdown')).toContainText(
    'no AI service connected',
    { timeout: 12000 },
  );
  await expect(
    page.getByRole('button', { name: 'Stop generating' }),
  ).toHaveCount(0);
  await page.reload();
  await page
    .getByRole('button', { name: 'Hello, a new idea', exact: true })
    .click();
  await expect(page.locator('.user-text')).toHaveText('Hello, a new idea');
  await expect(page.locator('.assistant .markdown')).toContainText(
    'no AI service connected',
  );
});

test('stop cancels streaming without modifying later conversations', async ({
  page,
}) => {
  await page
    .getByRole('textbox', { name: 'Message Kett' })
    .fill('Write a Svelte to-do component');
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  await page.waitForTimeout(250);
  await page.getByRole('button', { name: 'Stop generating' }).click();
  const partial = await page.locator('.assistant .markdown').textContent();
  await page.waitForTimeout(250);
  await expect(page.locator('.assistant .markdown')).toHaveText(partial!);
  await page.getByRole('button', { name: /New conversation/ }).click();
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
});

test('search shortcut filters and opens saved conversations', async ({
  page,
}) => {
  await page.keyboard.press('Control+k');
  const dialog = page.getByRole('dialog', { name: 'Search conversations' });
  await expect(dialog).toBeVisible();
  await expect(
    page.getByRole('textbox', { name: 'Search conversation titles' }),
  ).toBeFocused();
  await page
    .getByRole('textbox', { name: 'Search conversation titles' })
    .fill('Svelte');
  await expect(
    dialog.getByRole('button', { name: /Exploring Svelte/ }),
  ).toHaveCount(1);
  await dialog.getByRole('button', { name: /Exploring Svelte/ }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.locator('.markdown pre')).toContainText('$state');
});

test('creates a local project and starts a scoped conversation', async ({
  page,
}) => {
  await page.getByRole('button', { name: /My projects/ }).click();
  await page
    .getByRole('textbox', { name: 'New project name' })
    .fill('Weekend lab');
  await page
    .getByRole('button', { name: 'Create project', exact: true })
    .click();
  await page.getByRole('button', { name: /Weekend lab/ }).click();
  await expect(page.locator('.breadcrumb')).toContainText('Weekend lab');
  await page
    .getByRole('textbox', { name: 'Message Kett' })
    .fill('Notes for my project');
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  await page.getByRole('button', { name: 'Stop generating' }).click();
  await page.getByRole('button', { name: /My projects/ }).click();
  await expect(page.getByRole('button', { name: /Weekend lab/ })).toContainText(
    '1 conversation',
  );
});

test('downloads sample HTML directly from the conversation', async ({
  page,
}) => {
  await page
    .getByRole('textbox', { name: 'Message Kett' })
    .fill('Design a website');
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  const download = page
    .getByRole('log')
    .getByRole('button', { name: 'Download HTML' });
  await expect(download).toBeVisible({ timeout: 12000 });
  const downloadPromise = page.waitForEvent('download');
  await download.click();
  expect((await downloadPromise).suggestedFilename()).toBe(
    'slow-isle-cafe.html',
  );
  await expect(page.locator('iframe')).toHaveCount(0);
});

test('header theme persists and settings show signed-out status', async ({
  page,
}) => {
  const theme = page
    .locator('.topbar')
    .getByRole('button', { name: 'Dark appearance' });
  await expect(theme).toHaveAttribute('aria-pressed', 'false');
  await theme.click();
  await expect(page.locator('.app-shell')).toHaveClass(/dark/);
  await page.screenshot({ path: 'test-results/welcome-dark.png' });
  await page.reload();
  await expect(theme).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.app-shell')).toHaveClass(/dark/);
  await theme.click();
  await expect(page.locator('.app-shell')).not.toHaveClass(/dark/);
  await page.getByRole('button', { name: 'Open workspace settings' }).click();
  const settings = page.getByRole('dialog', { name: 'Workspace settings' });
  await expect(settings.getByText('Guest', { exact: true })).toBeVisible();
  await expect(
    settings.getByRole('button', { name: 'Try demo sign-in' }),
  ).toBeVisible();
  await expect(settings.getByText('Lin', { exact: true })).toHaveCount(0);
  await expect(settings.getByText(/your own little space/i)).toHaveCount(0);
  await expect(settings.getByLabel('Dark appearance')).toHaveCount(0);
});

test('clearing history requires confirmation', async ({ page }) => {
  await page.getByRole('button', { name: 'Open workspace settings' }).click();
  await page.getByRole('button', { name: 'Clear', exact: true }).click();
  await expect(page.locator('.history-item')).toHaveCount(3);
  await page
    .getByRole('button', { name: 'Confirm clear?', exact: true })
    .click();
  await expect(page.locator('.history-item')).toHaveCount(0);
});

test('accepts an arbitrary attachment and sends it through general chat', async ({
  page,
}) => {
  await page.route('**/api/models', (route) =>
    route.fulfill({ json: ['general'] }),
  );
  await page.reload();
  await page.route('**/api/chat/attachments', async (route) => {
    const body = route.request().postData()!;
    expect(body).toContain('filename="slides.pdf"');
    expect(body).toContain('%PDF-1.7');
    expect(body).toContain('Summarize these slides');
    await route.fulfill({
      body:
        JSON.stringify({ type: 'text', text: 'I cannot read this PDF.' }) +
        '\n',
    });
  });
  await page.getByLabel('Choose attachments').setInputFiles({
    name: 'slides.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.7'),
  });
  await expect(page.locator('.attachment')).toContainText('slides.pdf');
  const send = page.getByRole('button', { name: 'Send message', exact: true });
  await expect(send).toBeDisabled();
  await page.getByRole('button', { name: 'Select model' }).click();
  await page.getByRole('button', { name: 'general', exact: true }).click();
  await page.getByLabel('Message Kett').fill('Summarize these slides');
  await send.click();
  await expect(page.locator('.assistant .markdown')).toHaveText(
    'I cannot read this PDF.',
  );
  await expect(
    page.getByRole('button', { name: 'Download notebook' }),
  ).toHaveCount(0);
  await page.getByRole('button', { name: 'Remove slides.pdf' }).click();
  await expect(page.locator('.attachment')).toHaveCount(0);
});

test('uses a separate Report Agent model for a follow-up about the attached table', async ({
  page,
}) => {
  await page.route('**/api/models', (route) =>
    route.fulfill({ json: ['general', 'writer'] }),
  );
  await page.reload();
  const settings = page.getByRole('button', {
    name: 'Open workspace settings',
  });
  await settings.click();
  await page.getByRole('tab', { name: 'Tools' }).click();
  const reportModel = page.getByRole('combobox', {
    name: /Report Agent model/,
  });
  await expect(reportModel).toHaveValue('');
  await reportModel.selectOption('writer');
  const basic = page.getByRole('switch', { name: 'Basic', exact: true });
  const advanced = page.getByRole('switch', { name: 'Advanced', exact: true });
  await expect(basic).toBeChecked();
  await expect(basic).toBeDisabled();
  await expect(advanced).not.toBeChecked();
  await advanced.click();
  await expect(basic).toBeEnabled();
  await basic.click();
  await expect(basic).not.toBeChecked();
  await expect(advanced).toBeDisabled();
  await basic.click();
  await page.reload();
  await settings.click();
  await page.getByRole('tab', { name: 'Tools' }).click();
  await expect(reportModel).toHaveValue('writer');
  await expect(basic).toBeChecked();
  await expect(advanced).toBeChecked();
  await page.getByRole('button', { name: 'Close settings' }).click();
  await page.getByRole('button', { name: 'Select model' }).click();
  await page.getByRole('button', { name: 'general', exact: true }).click();

  const png =
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j0xkAAAAASUVORK5CYII=';
  const notebook = {
    nbformat: 4,
    nbformat_minor: 5,
    metadata: {},
    cells: [
      {
        cell_type: 'markdown',
        id: 'basic',
        metadata: { kett_report_mode: 'ollama' },
        source: '# Basic — Data summary\n\nMean score for grades.csv',
        attachments: {},
      },
      {
        cell_type: 'markdown',
        id: 'advanced',
        metadata: { kett_report_mode: 'ollama' },
        source:
          '# Advanced — Regression analysis report\n\n![Chart](attachment:chart.png)',
        attachments: { 'chart.png': { 'image/png': png } },
      },
    ],
  };
  let requests = 0;
  await page.route('**/api/chat/attachments', async (route) => {
    const body = route.request().postData()!;
    expect(body).toContain('filename="grades.csv"');
    expect(body).toContain('score,hours,practice');
    expect(body).toContain('"model":"general"');
    expect(body).toContain('"report_model":"writer"');
    expect(body).toContain('"mat_enabled":true');
    expect(body).toContain('"report_levels":["basic","advanced"]');
    const event =
      ++requests === 1
        ? {
            type: 'text',
            text: 'Which column do you want to predict, and which features should I use?',
          }
        : { type: 'report', notebook };
    if (requests === 2) {
      expect(body).toContain('Build a model for this table');
      expect(body).toContain('Predict score using hours');
    }
    await route.fulfill({ body: JSON.stringify(event) + '\n' });
  });
  await page.getByLabel('Choose attachments').setInputFiles({
    name: 'grades.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('score,hours,practice\n8,1,2\n'),
  });
  const prompt = page.getByLabel('Message Kett');
  await prompt.fill('Build a model for this table');
  await prompt.press('Enter');
  await expect(page.locator('.assistant .markdown')).toContainText(
    'Which column',
  );
  await expect(page.locator('.attachment')).toContainText('grades.csv');
  await prompt.fill('Predict score using hours');
  await prompt.press('Enter');
  await expect(
    page.getByRole('heading', { name: 'Basic — Data summary' }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', {
      name: 'Advanced — Regression analysis report',
    }),
  ).toBeVisible();
  await expect(page.getByRole('img', { name: 'Chart' })).toHaveAttribute(
    'src',
    /^data:image\/png;base64,/,
  );
  const downloaded = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download notebook' }).click();
  const file = await downloaded;
  expect(file.suggestedFilename()).toBe('report.ipynb');
  expect(JSON.parse(await readFile(await file.path(), 'utf8'))).toEqual(
    notebook,
  );
});

test('the Tools tab preserves the MAT switch across reloads and sends the preference', async ({
  page,
}) => {
  await page.route('**/api/models', (route) =>
    route.fulfill({ json: ['general'] }),
  );
  await page.reload();
  const settings = page.getByRole('button', {
    name: 'Open workspace settings',
  });
  const tools = page.getByRole('tab', { name: 'Tools' });
  const toggle = page.getByRole('switch', {
    name: 'Multi-Agent Data Analysis',
  });
  await settings.click();
  await page.getByRole('tab', { name: 'General' }).focus();
  await page.keyboard.press('ArrowRight');
  await expect(tools).toBeFocused();
  await expect(tools).toHaveAttribute('aria-selected', 'true');
  await expect(toggle).toBeChecked();
  await toggle.click();
  await expect(
    page.getByRole('combobox', { name: /Report Agent model/ }),
  ).toBeDisabled();
  await expect(page.getByRole('switch', { name: 'Advanced' })).toBeDisabled();
  await page.reload();
  await settings.click();
  await tools.click();
  await expect(toggle).not.toBeChecked();
  await page.getByRole('button', { name: 'Close settings' }).click();
  await page.getByRole('button', { name: 'Select model' }).click();
  await page.getByRole('button', { name: 'general', exact: true }).click();
  let requests = 0;
  await page.route('**/api/chat/attachments', (route) => {
    requests += 1;
    expect(route.request().postData()).toContain(
      `"mat_enabled":${requests > 1}`,
    );
    return route.fulfill({
      body:
        JSON.stringify({ type: 'text', text: `Replied ${requests}` }) + '\n',
    });
  });
  await page.getByLabel('Choose attachments').setInputFiles({
    name: 'grades.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('score,hours\n8,1\n'),
  });
  const prompt = page.getByLabel('Message Kett');
  await prompt.fill('What are the columns?');
  await prompt.press('Enter');
  await expect(page.getByText('Replied 1', { exact: true })).toBeVisible();
  await settings.click();
  await tools.click();
  await toggle.click();
  await expect(toggle).toBeChecked();
  await page.getByRole('button', { name: 'Close settings' }).click();
  await prompt.fill('What are the columns?');
  await prompt.press('Enter');
  await expect(page.getByText('Replied 2', { exact: true })).toBeVisible();
});

test('mobile layout, drawer navigation and composer stay within the viewport', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('.sidebar')).not.toBeInViewport();
  await page.screenshot({ path: 'test-results/welcome-mobile.png' });
  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
    const toolbar = page.locator('.composer-toolbar');
    expect(
      await toolbar.evaluate((node) => node.scrollWidth <= node.clientWidth),
    ).toBeTruthy();
  }
  await page.getByRole('button', { name: 'Expand sidebar' }).click();
  await page
    .getByRole('button', { name: 'Exploring Svelte 5', exact: true })
    .click();
  await expect(page.locator('.mobile-scrim')).toHaveCount(0);
  await expect(
    page.getByRole('textbox', { name: 'Message Kett' }),
  ).toBeInViewport();
  await expect(
    page.getByRole('button', { name: 'Dark appearance' }),
  ).toBeInViewport();
});

test('markdown from stored conversations is sanitized', async ({ page }) => {
  await page.evaluate(() => {
    const data = JSON.parse(localStorage.getItem('kett-workspace-v1')!);
    data.conversations.unshift({
      id: 'unsafe',
      title: 'Security check',
      updatedAt: Date.now(),
      messages: [
        {
          id: 'unsafe-message',
          role: 'assistant',
          content:
            '<img src="x" onerror="window.__unsafe=true"><script>window.__unsafe=true</script>Safe text',
        },
      ],
    });
    localStorage.setItem('kett-workspace-v1', JSON.stringify(data));
  });
  await page.reload();
  await page
    .getByRole('button', { name: 'Security check', exact: true })
    .click();
  await expect(page.locator('.markdown')).toContainText('Safe text');
  await expect(
    page.locator('.markdown script, .markdown [onerror]'),
  ).toHaveCount(0);
  expect(await page.evaluate(() => '__unsafe' in window)).toBeFalsy();
});

test('existing demo data becomes English without deleting user content', async ({
  page,
}) => {
  await page.evaluate(() => {
    localStorage.setItem(
      'kett-workspace-v1',
      JSON.stringify({
        dark: true,
        projects: ['个人网站', '灵感收集站', 'My own project'],
        conversations: [
          {
            id: 'welcome-svelte',
            title: '探索 Svelte 5 的新可能',
            updatedAt: Date.now(),
            project: '个人网站',
            messages: [
              {
                id: 's3',
                role: 'user',
                content: 'Svelte 5 的 $state 应该怎么用？',
              },
              { id: 's4', role: 'assistant', content: '旧示例回复' },
              { id: 'my-message', role: 'user', content: '保留我的原始消息' },
            ],
          },
          {
            id: 'my-chat',
            title: '我自己的对话',
            updatedAt: Date.now(),
            messages: [
              { id: 'custom', role: 'user', content: '不要修改我的内容' },
            ],
          },
        ],
      }),
    );
  });
  await page.reload();
  await expect(page.locator('.app-shell')).toHaveClass(/dark/);
  await page
    .getByRole('button', { name: 'Exploring Svelte 5', exact: true })
    .click();
  await expect(page.locator('.breadcrumb')).toContainText('Personal website');
  await expect(page.locator('.markdown')).toContainText('reactive state');
  await expect(page.locator('.user-text').last()).toHaveText(
    '保留我的原始消息',
  );
  await page.getByRole('button', { name: '我自己的对话', exact: true }).click();
  await expect(page.locator('.user-text')).toHaveText('不要修改我的内容');
  await page.getByRole('button', { name: /My projects/ }).click();
  await expect(
    page
      .getByRole('dialog')
      .getByRole('button', { name: /Ideas & inspiration/ }),
  ).toBeVisible();
  await expect(
    page.getByRole('dialog').getByRole('button', { name: /My own project/ }),
  ).toBeVisible();
});

test('all default interface surfaces and demo messages are English', async ({
  page,
}) => {
  const expectEnglish = async () => {
    expect(await page.locator('body').innerText()).not.toMatch(
      /\p{Script=Han}/u,
    );
  };
  await expectEnglish();
  await page.getByRole('button', { name: 'Open workspace settings' }).click();
  await expectEnglish();
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: /My projects/ }).click();
  await expectEnglish();
  await page.keyboard.press('Escape');
  await page.keyboard.press('Control+k');
  await expectEnglish();
  await page.keyboard.press('Escape');
  for (const title of [
    'A little room to breathe',
    'Exploring Svelte 5',
    'A lighter kind of weekly plan',
  ]) {
    await page.getByRole('button', { name: title, exact: true }).click();
    await expectEnglish();
  }
});
