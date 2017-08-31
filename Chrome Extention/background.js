chrome.tabs.onUpdated.addListener(function(tabId, changedInfo, tab) {
    for (site in GB.getBlockedSites()) {
        if (tab.url.match(site)) {
            chrome.tabs.update(tabId, {"url" : GB.getWatchThisInstead()}, 
function () {});
        }
    }
});