import { test, expect } from '@playwright/test';

test('type sizes are 125% of the original across interface surfaces', async ({
  page,
}) => {
  await page.goto('/');
  await expect(page.locator('.new-chat')).toHaveCSS('font-size', '15px');
  await expect(page.locator('.composer textarea')).toHaveCSS(
    'font-size',
    '15px',
  );
  await expect(page.locator('.history-link').first()).toHaveCSS(
    'font-size',
    '14.375px',
  );
  await expect(page.locator('.suggestion-card strong').first()).toHaveCSS(
    'font-size',
    '13.75px',
  );
  await page.getByRole('button', { name: 'Open workspace settings' }).click();
  await expect(
    page.getByRole('heading', { name: 'Workspace settings' }),
  ).toHaveCSS('font-size', '31.25px');
  await page.keyboard.press('Escape');
  await page
    .getByRole('button', { name: 'Exploring Svelte 5', exact: true })
    .click();
  await expect(page.locator('.markdown')).toHaveCSS('font-size', '15px');
  await expect(page.locator('.markdown pre')).toHaveCSS('font-size', '12.5px');
});

test('larger type remains contained across desktop, tablet and mobile sizes', async ({
  page,
}) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  for (const width of [1920, 1440, 1024, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    for (const selector of [
      '.welcome-scroll',
      '.composer-toolbar',
      '.suggestions',
      '.topbar',
    ]) {
      const element = page.locator(selector);
      expect(
        await element.evaluate(
          (node) => node.scrollWidth <= node.clientWidth + 1,
        ),
        `${selector} at ${width}px`,
      ).toBeTruthy();
    }
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('.composer textarea')).toHaveCSS(
    'font-size',
    '15px',
  );
  await expect(page.locator('.welcome h1')).toHaveCSS('font-size', '28px');
  await page.getByRole('button', { name: 'Select model' }).click();
  const menu = await page.locator('.model-menu').boundingBox();
  expect(menu).not.toBeNull();
  expect(menu!.x).toBeGreaterThanOrEqual(0);
  expect(menu!.x + menu!.width).toBeLessThanOrEqual(390);
});
