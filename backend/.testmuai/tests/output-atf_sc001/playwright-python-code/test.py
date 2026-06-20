import os
import testmu
from testmu import expect, var, set_var
from playwright.async_api import Page

testmu.configure(
    build="050e193e-3869-4e85-b854-4f50742eddb0",
    name="Add Product to Cart and Verify Count",
    tc_id="TC-44854",
    network=os.getenv("NETWORK", "false").lower() == "true",
    default_action_timeout_ms=10000,
    default_navigation_timeout_ms=30000,
    kane_run_v4=True,
)

async def _resolve_ranked_locator(page, locators, description=""):
    """Return the first locator in *locators* that matches at least one element.

    Mirrors Selenium's ranked-selector iteration: tries each locator in the
    order supplied and stops at the first match, preserving selector rank
    priority rather than DOM order (which .or_().first would use).

    When no locator resolves:
      - description provided (V3 path): returns ``testmu.locator(page,
        description=description)`` — a VisionLocator that triggers the heal
        cascade when its action method is awaited.
      - description omitted (V4 path): raises ``TimeoutError``.
    """
    for _loc in locators:
        if await _loc.count() > 0:
            return _loc
    if description:
        import testmu
        return testmu.locator(page, description=description)
    raise TimeoutError("ranked locator resolution exhausted — no selector matched")


@testmu.test
async def test(page: Page):
    async with testmu.step('Navigate to https://ecommerce-playground.lambdatest.io/', instruction_id='b33957f5-010a-4dbb-870f-194a9dd61dd4'):
        await page.goto("https://ecommerce-playground.lambdatest.io/")
    
    async with testmu.step('Clicking SHOP NOW to open a product page', instruction_id='b944edbf-7d02-43e9-be15-d8be82aeb1ed'):
        _loc_1 = page.locator("#entry_218384 >> internal:role=link[name=\"SHOP NOW\"i]")
        
        await _loc_1.click()
    
    async with testmu.step('Typing a product keyword in the search box', instruction_id='31882328-a788-42dd-95f2-bd69c06e2179'):
        element_0 = page.locator("internal:role=textbox[name=\"Search For Products\"i]")
        
        await element_0.click()
        await element_0.fill("camera")
    
    async with testmu.step('PRIMARY: Search submit button; role=button; text="SEARCH" | HINTS: container=header; to the right of the search input', instruction_id='cb5b452b-c511-43ee-8dfc-4f3e20929ac9'):
        coords = await testmu.get_vision_coordinates(page, 'PRIMARY: Search submit button; role=button; text="SEARCH" | HINTS: container=header; to the right of the search input', "click", 1272, 43)
        await page.mouse.click(coords['x'], coords['y'])
        
    
    async with testmu.step('Going back to the homepage from empty search results', instruction_id='2f556ec8-f130-46c3-83f6-28a3e03d30de'):
        _loc_2 = page.locator("#widget-navbar-217834 >> internal:role=link[name=\"Home\"i]")
        
        await _loc_2.click()
    
    async with testmu.step('Scrolling down to find product listings', instruction_id='77a06ca5-b7ee-412e-87d0-f3062716a4a6'):
        await page.wait_for_load_state('domcontentloaded', timeout=5000)
        await page.evaluate('window.scrollBy(0, 800)')
    
    async with testmu.step('Opening the Microsoft smartwatch product page', instruction_id='ec23ebf9-4b36-4f55-80be-4a79eb3f96de'):
        _loc_3 = page.locator(".carousel-inner > div:nth-child(2) > a")
        
        await _loc_3.click()
    
    async with testmu.step('Scrolling down to find the Add to Cart button', instruction_id='70b1d166-9efb-4fa1-b7af-520e35e22bb0'):
        await page.wait_for_load_state('domcontentloaded', timeout=5000)
        await page.evaluate('window.scrollBy(0, 46)')
    
    async with testmu.step('Opening the Software category from breadcrumb', instruction_id='933488c7-de47-4c95-9b49-c221c61cdf7c'):
        _loc_4 = page.locator("internal:label=\"breadcrumb\"i >> internal:role=link[name=\"Software\"i]")
        
        await _loc_4.click()
    
    async with testmu.step('Opening the Canon EOS 5D product page', instruction_id='52109d75-6c89-4f1a-83a5-88a7f5dd1976'):
        _loc_5 = page.locator("internal:role=link[name=\"Canon EOS 5D\"s]")
        
        await _loc_5.click()
    
    async with testmu.step('Opening the Size dropdown', instruction_id='8b16be8c-02b1-40db-b7c5-bda6f6c2ff2c'):
        _loc_6 = page.locator("#input-option230-216836")
        
        await _loc_6.click()
    
    async with testmu.step('Opening the Size dropdown', instruction_id='afb1a224-c60a-4bb6-ba69-e34d361b6354'):
        _loc_7 = page.locator("#input-option230-216836")
        
        await _loc_7.click()
    
    async with testmu.step('Opening the Size dropdown on the product page', instruction_id='b0997158-b7b4-4867-8a21-aa8c83425dd5'):
        _loc_8 = page.locator("#input-option230-216836")
        
        await _loc_8.click()
    
    async with testmu.step('Opening the Size dropdown on the product page', instruction_id='69c3b09f-9ceb-4e3a-b9ba-21ce1404516b'):
        _loc_9 = page.locator("#input-option230-216836")
        
        await _loc_9.click()


if __name__ == "__main__":
    testmu.run(test)