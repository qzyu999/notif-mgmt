import { expect, test } from "@playwright/test";

// Complete synthetic Today workflow: understand a candidate, resolve its
// identity explicitly, decide its state, and verify persistence after reload.
test("today identity and triage workflow persists", async ({ page }) => {
  await page.goto("/#/today");
  const taylorCard = page.locator("article", { hasText: "taylor@example.invalid" });
  await expect(taylorCard).toBeVisible();
  await expect(taylorCard.getByText(/Direct email via email/)).toBeVisible();
  await expect(taylorCard.getByText(/understand the privacy model/)).toBeVisible();
  await expect(taylorCard.getByText(/Identity unresolved/)).toBeVisible();

  await taylorCard.getByRole("button", { name: "Resolve identity" }).click();
  await expect(taylorCard.getByText(/Nothing is linked until you confirm/)).toBeVisible();
  await taylorCard.getByRole("button", { name: "Create person" }).click();
  await expect(taylorCard.getByRole("button", { name: "Confirm link to Taylor" }))
    .toBeVisible();
  await taylorCard.getByRole("button", { name: "Confirm link to Taylor" }).click();
  await expect(page.getByText(/Identity taylor@example\.invalid linked to Taylor/))
    .toBeVisible();
  await expect(taylorCard.getByText(/Identity linked/)).toBeVisible();

  await taylorCard.getByRole("button", { name: "Mark as needs reply" }).click();
  await expect(page.getByText(/Taylor's item is now marked as needing a reply/))
    .toBeVisible();
  await expect(taylorCard).toHaveCount(0);

  const alexCard = page.locator("article", { hasText: "Interested in testing" });
  await expect(alexCard.getByText(/Name candidate only/)).toBeVisible();
  await alexCard.getByRole("button", { name: "Snooze 7 days" }).click();
  await expect(page.getByText(/Alex's item was snoozed for 7 days/)).toBeVisible();
  await expect(alexCard).toHaveCount(0);

  await page.goto("/#/followups");
  const confirmedTaylor = page.locator("article", { hasText: "understand the privacy model" });
  await expect(confirmedTaylor.getByText("You confirmed")).toBeVisible();
  await confirmedTaylor.getByRole("link", { name: "Open person" }).click();
  await expect(page.getByText(/taylor@example\.invalid on email \(Linked/)).toBeVisible();
  await expect(page.getByText(/Needs reply \/ Open/)).toBeVisible();
  await expect(page.getByText(/I'd like to understand the privacy model/)).toBeVisible();

  await page.goto("/#/followups");
  await page.getByLabel("Status").selectOption("snoozed");
  const snoozedAlex = page.locator("article", { hasText: "Interested in testing" });
  await expect(snoozedAlex).toBeVisible();
  await snoozedAlex.getByRole("button", { name: "Dismiss" }).click();
  await expect(snoozedAlex).toHaveCount(0);
  await page.getByLabel("Status").selectOption("dismissed");
  await expect(page.locator("article", { hasText: "Interested in testing" }))
    .toBeVisible();

  await page.reload();
  // The status filter is view state and resets to "open" on reload; the
  // persisted decision is proven by re-selecting "dismissed".
  await page.getByLabel("Status").selectOption("dismissed");
  await expect(page.locator("article", { hasText: "Interested in testing" }))
    .toBeVisible();

  const followups = await page.request.get("http://127.0.0.1:8000/api/v1/followups");
  const followupRows = await followups.json();
  const taylorFollowup = followupRows.find((row: { signal_id: number }) => row.signal_id === 3);
  const alexFollowup = followupRows.find((row: { signal_id: number }) => row.signal_id === 1);
  expect(taylorFollowup).toMatchObject({ kind: "reply", status: "open", person_id: 1 });
  expect(alexFollowup).toMatchObject({ kind: "review", status: "dismissed" });

  const identities = await page.request.get("http://127.0.0.1:8000/api/v1/identities");
  const identityRows = await identities.json();
  expect(identityRows.find(
    (row: { value_normalized: string }) =>
      row.value_normalized === "taylor@example.invalid",
  )).toMatchObject({
    person_id: 1,
    match_status: "verified",
    match_method: "manual",
  });
});
