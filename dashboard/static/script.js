// static/script.js

document.addEventListener('DOMContentLoaded', function() {

    async function updateStats() {
        try {
            const response = await fetch('/api/status');
            if (!response.ok) {
                console.error('Failed to fetch stats, server responded with status:', response.status);
                return;
            }

            const data = await response.json();
            
            // This is the refined section
            if (data && !data.error) {
                // Find the guild-count element
                const guildCountElem = document.getElementById('guild-count');
                // Only update it if it was found
                if (guildCountElem) {
                    guildCountElem.textContent = data.guild_count;
                }

                // Find the latency element
                const latencyElem = document.getElementById('latency');
                // Only update it if it was found
                if (latencyElem) {
                    latencyElem.textContent = data.latency_ms;
                }
            }
        } catch (error) {
            console.error('An error occurred while fetching stats:', error);
        }
    }

    // Call the function immediately on page load
    updateStats();

    // Then, call the function every 5 seconds
    setInterval(updateStats, 5000);

});