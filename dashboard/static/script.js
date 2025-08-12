// static/script.js
document.addEventListener('DOMContentLoaded', function() {

    function formatUptime(seconds) {
        const days = Math.floor(seconds / (3600 * 24));
        seconds %= (3600 * 24);
        const hours = Math.floor(seconds / 3600);
        seconds %= 3600;
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = Math.floor(seconds % 60);

        return `${days}d ${hours}h ${minutes}m ${remainingSeconds}s`;
    }

    function connectWebSocket() {
        // Use the current host to build the WebSocket URL
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsHost = window.location.host;
        const wsUrl = `${wsProtocol}//${wsHost}/ws/stats`;

        const websocket = new WebSocket(wsUrl);

        websocket.onopen = function(event) {
            console.log("WebSocket connected.");
        };

        websocket.onmessage = function(event) {
            const data = JSON.parse(event.data);
            
            // Bot Stats
            document.getElementById('latency').textContent = data.bot.latency_ms + ' ms';
            document.getElementById('guild-count').textContent = data.bot.guild_count;
            document.getElementById('user-count').textContent = data.bot.user_count;
            document.getElementById('channel-count').textContent = data.bot.channel_count;

            // System Stats
            document.getElementById('cpu-percent').textContent = data.system.cpu_percent + '%';
            document.getElementById('ram-used').textContent = data.system.ram_used_gb + ' GB';
            document.getElementById('ram-total').textContent = data.system.ram_total_gb + ' GB';
            document.getElementById('ram-percent').textContent = data.system.ram_percent + '%';
            document.getElementById('uptime').textContent = formatUptime(data.system.uptime_seconds);
            document.getElementById('net-sent').textContent = data.system.network_io_sent_mb + ' MB';
            document.getElementById('net-recv').textContent = data.system.network_io_recv_mb + ' MB';
        };

        websocket.onclose = function(event) {
            console.log("WebSocket disconnected. Attempting to reconnect in 5 seconds...");
            setTimeout(connectWebSocket, 5000);
        };

        websocket.onerror = function(error) {
            console.error("WebSocket error:", error);
            websocket.close();
        };
    }

    connectWebSocket();
});