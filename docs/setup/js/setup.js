// Initialize all event listeners when the DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    // Advanced setup button
    const advancedSetupButton = document.getElementById('advanced-setup-button');
    if (advancedSetupButton) {
        advancedSetupButton.addEventListener('click', startAdvancedSetup);
    }
    
    // Add other event listeners here as needed
});
 