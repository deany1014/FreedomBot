// static/script.js

document.addEventListener('DOMContentLoaded', function() {
    // Get the security key from the meta tag
    const dashboardKey = document.querySelector('meta[name="dashboard-key"]').content;

    async function updateStats() {
        try {
            const response = await fetch('/api/status', {
                headers: {
                    'X-DASHBOARD-KEY': dashboardKey
                }
            });

            if (!response.ok) {
                console.error('Failed to fetch stats, server responded with status:', response.status);
                // Optionally update a status element on the page
                document.getElementById('status').textContent = 'Error';
                return;
            }

            const data = await response.json();
            
            document.getElementById('guild-count').textContent = data.guild_count;
            document.getElementById('latency').textContent = data.latency_ms + ' ms';
            document.getElementById('server-name').textContent = data.server_name;
            document.getElementById('status').textContent = 'Online';
        } catch (error) {
            console.error('An error occurred while fetching stats:', error);
            document.getElementById('status').textContent = 'Error';
        }
    }

    // Call the function immediately on page load
    updateStats();

    // Then, call the function every 5 seconds
    setInterval(updateStats, 5000);
});