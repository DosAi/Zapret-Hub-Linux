--[[
  Zapret Hub — YouTube / Discord bypass seed for winws2 (Zapret 2).
  Catalogs mirror Flowseal/FluxRoute-style lists. Packet desync is applied by
  Hub orchestrator Lua (hub_tls / hub_http / hub_quic / hub_discord) and
  --hostlist / --ipset files that Hub materializes. This file is loaded via
  --lua-init so the preset stays available in Manual and Auto modes.
]]

HUB_BYPASS_YOUTUBE_DISCORD = true
HUB_BYPASS_YOUTUBE_DISCORD_VERSION = "1"

-- Domain catalog (hostlist files are authoritative; this mirrors them for Lua).
HUB_BYPASS_DOMAINS = {
  "discord.com",
  "discordapp.com",
  "discord.gg",
  "discord.media",
  "discordcdn.com",
  "discordstatus.com",
  "cdn.discordapp.com",
  "media.discordapp.net",
  "gateway.discord.gg",
  "images-ext-1.discordapp.net",
  "images-ext-2.discordapp.net",
  "dl.discordapp.net",
  "status.discord.com",
  "latency.discord.media",
  "updates.discord.com",
  "youtube.com",
  "youtu.be",
  "ytimg.com",
  "googlevideo.com",
  "youtube-nocookie.com",
  "ggpht.com",
  "gvt1.com",
  "youtube.googleapis.com",
  "youtubei.googleapis.com",
  "yt3.googleusercontent.com",
  "manifest.googlevideo.com",
  "redirector.googlevideo.com",
}

HUB_BYPASS_NETWORKS = {
  "149.154.167.0/24",
  "173.194.0.0/16",
  "162.159.128.0/20",
}

if type(print) == "function" then
  print(string.format(
    "[Zapret Hub] YouTube/Discord bypass Lua ready (domains=%d networks=%d)",
    #HUB_BYPASS_DOMAINS,
    #HUB_BYPASS_NETWORKS
  ))
end
