import { expect, test } from "@playwright/test";

// Golden path over synthetic demo fixtures only:
// review candidate -> create person -> link identity -> complete follow-up.
test("manual triage golden path", async ({ page }) => {
  await page.goto("/#/followups");
  await expect(page.getByText(/Direct message notification via LinkedIn/)).toBeVisible();

  await page.goto("/#/people");
  await page.getByLabel("New person name").fill("Taylor");
  await page.getByRole("button", { name: "Create person" }).click();
  await expect(page.getByRole("link", { name: "Taylor" })).toBeVisible();

  await page.getByRole("link", { name: "Taylor" }).click();
  await page
    .getByRole("button", { name: "Link to Taylor" })
    .first()
    .click();
  await expect(page.getByText(/taylor@example\.invalid on email \(Linked/))
    .toBeVisible();

  await page.goto("/#/followups");
  await page.getByRole("button", { name: "Done" }).first().click();
  // Let the open-list refetch settle before switching filters, so a slow
  // response cannot overwrite the done list afterwards.
  await expect(page.getByRole("button", { name: "Done" })).toHaveCount(1);
  await page.getByLabel("Status").selectOption("done");
  await expect(page.getByRole("button", { name: "Reopen" }).first())
    .toBeVisible();

  await page.goto("/#/today");
  await expect(page.getByRole("heading", { name: "Review candidates" })).toBeVisible();
  await page.goto("/#/sources");
  await expect(page.getByText(/sender-domain matching/)).toBeVisible();
});
