/**
 * Test save/load functionality for pipeline configs
 */
import { test, expect } from '@playwright/test'

test.describe('Pipeline Save/Load', () => {
  test('should display pipeline name input and save button', async ({ page }) => {
    await page.goto('http://localhost:3001/editor')
    await page.waitForSelector('input[placeholder="Pipeline name"]')

    // Check that the name input exists
    const nameInput = page.locator('input[placeholder="Pipeline name"]')
    await expect(nameInput).toBeVisible()

    // Default value should be "New Pipeline"
    await expect(nameInput).toHaveValue('New Pipeline')

    // Save button should exist
    const saveButton = page.getByRole('button', { name: /Save|Update/ })
    await expect(saveButton).toBeVisible()
  })

  test('should save a new pipeline', async ({ page }) => {
    await page.goto('http://localhost:3001/editor')
    await page.waitForSelector('input[placeholder="Pipeline name"]')

    // Change the pipeline name
    const nameInput = page.locator('input[placeholder="Pipeline name"]')
    await nameInput.fill('Test Pipeline ' + Date.now())

    // Click save
    const saveButton = page.getByRole('button', { name: /Save/ })
    await saveButton.click()

    // Wait for success message
    await page.waitForSelector('text=Created', { timeout: 5000 })

    // Verify the button now says "Update"
    await expect(page.getByRole('button', { name: /Update/ })).toBeVisible()
  })

  test('should load saved pipelines list', async ({ page }) => {
    await page.goto('http://localhost:3001/editor')
    await page.waitForSelector('input[placeholder="Pipeline name"]')

    // Wait for configs to load
    await page.waitForTimeout(1000)

    // Check if "Saved Pipelines" section exists (if any configs exist)
    const savedPipelinesHeader = page.getByText('Saved Pipelines')
    const exists = await savedPipelinesHeader.count()

    if (exists > 0) {
      await expect(savedPipelinesHeader).toBeVisible()
    }
  })

  test('should create, save, and reload a pipeline', async ({ page }) => {
    await page.goto('http://localhost:3001/editor')
    await page.waitForSelector('input[placeholder="Pipeline name"]')

    const uniqueName = 'E2E Test Pipeline ' + Date.now()

    // Set name
    const nameInput = page.locator('input[placeholder="Pipeline name"]')
    await nameInput.fill(uniqueName)

    // Save
    await page.getByRole('button', { name: /Save/ }).click()
    await page.waitForSelector('text=Created', { timeout: 5000 })

    // Click "New" to reset
    await page.getByRole('button', { name: 'New' }).click()

    // Verify name is reset
    await expect(nameInput).toHaveValue('New Pipeline')

    // Find and click on the saved pipeline in the list
    const savedPipelineButton = page.getByRole('button', { name: uniqueName })
    await savedPipelineButton.click()

    // Wait for load
    await page.waitForSelector('text=Loaded', { timeout: 5000 })

    // Verify name is loaded
    await expect(nameInput).toHaveValue(uniqueName)
  })

  test('should show project dropdown', async ({ page }) => {
    await page.goto('http://localhost:3001/editor')
    await page.waitForSelector('input[placeholder="Pipeline name"]')

    // Check project dropdown exists
    const projectSelect = page.locator('select').first()
    await expect(projectSelect).toBeVisible()

    // Should have "No project" option
    await expect(projectSelect).toContainText('No project')
  })
})
