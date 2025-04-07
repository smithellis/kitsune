import "sumo/js/protocol";
import trackEvent from "sumo/js/analytics";

(function() {
  'use strict';
  
  document.addEventListener('DOMContentLoaded', function() {
    const langSelect = document.getElementById('mzp-c-language-switcher-select');
    
    if (langSelect) {
      // Store the original change handler
      const originalOnChange = langSelect.onchange;
      
      langSelect.onchange = function(event) {
        const currentLocale = document.documentElement.lang || 
                            document.querySelector('html').getAttribute('lang');
        const newLocale = this.value;
        const currentPath = window.location.pathname;
        
        // Extract the path without locale prefix
        const pathParts = currentPath.split('/');
        pathParts.splice(0, 2);
        const pathWithoutLocale = pathParts.join('/');
        
        let newUrl = '/' + newLocale + '/' + pathWithoutLocale;
        
        const queryString = window.location.search || '';
        let queryParams = new URLSearchParams(queryString);
        
        // Add source locale to handle documents with different slugs across locales
        queryParams.set('source_locale', currentLocale);
        
        if (window.location.hash) {
          const urlFragment = window.location.hash.substring(1);
          queryParams.set('redirect_url_fragment', urlFragment);
        }
        
        newUrl += '?' + queryParams.toString();
        
        trackEvent("footer.language-switcher", {
          "old_language": currentLocale,
          "new_language": newLocale,
        });
        
        window.location.href = newUrl;
        
        event.preventDefault();
        return false;
      };
    }
  });
})();
