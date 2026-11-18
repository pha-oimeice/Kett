import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
});

test('welcome, suggestions, model menu and keyboard composer', async ({
  page,
}) => {
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page).toHaveTitle('Kett — A space for possibility');
  await expect(
    page.getByRole('button', { name: 'Send message', exact: true }),
  ).toBeDisabled();
  await page.getByRole('button', { name: /Make something new/ }).click();
  await expect(page.getByRole('textbox', { name: 'Message Kett' })).toHaveValue(
    /coffee/,
  );
  await page
    .getByRole('button', { name: 'Claude Sonnet 4.5', exact: true })
    .click();
  await page.getByRole('button', { name: /Claude Opus 4.5/ }).click();
  await expect(
    page.getByRole('button', { name: 'Claude Opus 4.5', exact: true }),
  ).toBeVisible();
  await page
    .getByRole('textbox', { name: 'Message Kett' })
    .press('Shift+Enter');
  await expect(page.locator('.messages')).toHaveCount(0);
  await page.screenshot({ path: 'test-results/welcome-desktop.png' });
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

test('workbench previews HTML, shows source and downloads the artifact', async ({
  page,
}) => {
  await page.getByRole('button', { name: 'Workbench', exact: true }).click();
  const workbench = page.getByRole('complementary', { name: 'Code workbench' });
  await expect(workbench).toBeVisible();
  await expect(
    page.frameLocator('iframe').getByRole('heading', { level: 1 }),
  ).toContainText('A slower pace.');
  await page.screenshot({ path: 'test-results/workbench-desktop.png' });
  await workbench.getByRole('button', { name: 'Code', exact: true }).click();
  await expect(page.locator('.artifact-code')).toContainText('<!doctype html>');
  const downloadPromise = page.waitForEvent('download');
  await page
    .getByRole('button', { name: 'Download HTML', exact: true })
    .click();
  expect((await downloadPromise).suggestedFilename()).toBe(
    'slow-isle-cafe.html',
  );
  await page.getByRole('button', { name: 'Close workbench' }).click();
  await expect(workbench).toHaveCount(0);
});

test('theme persists and clearing history requires confirmation', async ({
  page,
}) => {
  await page.getByRole('button', { name: 'Open workspace settings' }).click();
  await page.getByRole('switch', { name: 'Dark appearance' }).click();
  await expect(page.locator('.app-shell')).toHaveClass(/dark/);
  await page.keyboard.press('Escape');
  await page.screenshot({ path: 'test-results/welcome-dark.png' });
  await page.reload();
  await expect(page.locator('.app-shell')).toHaveClass(/dark/);
  await page.getByRole('button', { name: 'Open workspace settings' }).click();
  await page.getByRole('button', { name: 'Clear', exact: true }).click();
  await expect(page.locator('.history-item')).toHaveCount(3);
  await page
    .getByRole('button', { name: 'Confirm clear?', exact: true })
    .click();
  await expect(page.locator('.history-item')).toHaveCount(0);
});

test('attachment metadata can be added and removed without uploading', async ({
  page,
}) => {
  await page.getByLabel('Choose attachments').setInputFiles({
    name: 'ideas.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('A new idea'),
  });
  await expect(page.locator('.attachment')).toContainText('ideas.txt');
  await expect(
    page.getByRole('button', { name: 'Send message', exact: true }),
  ).toBeEnabled();
  await page.getByRole('button', { name: 'Remove ideas.txt' }).click();
  await expect(page.locator('.attachment')).toHaveCount(0);
  await expect(
    page.getByRole('button', { name: 'Send message', exact: true }),
  ).toBeDisabled();
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
  await page.getByRole('button', { name: 'Workbench', exact: true }).click();
  await expect(
    page.getByRole('complementary', { name: 'Code workbench' }),
  ).toBeInViewport();
  await page.getByRole('button', { name: 'Close workbench' }).click();
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
