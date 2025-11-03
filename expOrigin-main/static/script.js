// Shared UI utilities to reduce duplication across templates
(function () {
  function qs(selector, root) { return (root || document).querySelector(selector); }

  function initNavbarUI() {
    const mobileMenuBtn = qs('.mobile-menu-btn');
    const navMenu = qs('.nav-menu');
    if (mobileMenuBtn && navMenu) {
      mobileMenuBtn.addEventListener('click', () => {
        navMenu.classList.toggle('active');
      });
    }
    const navbar = qs('.navbar');
    // Only apply auto background effect if explicitly enabled on the navbar
    if (navbar && navbar.hasAttribute('data-scroll-bg')) {
      window.addEventListener('scroll', () => {
        if (window.scrollY > 50) {
          navbar.style.background = 'rgba(255, 255, 255, 0.98)';
          navbar.style.boxShadow = '0 2px 30px rgba(0, 0, 0, 0.15)';
        } else {
          navbar.style.background = 'rgba(255, 255, 255, 0.95)';
          navbar.style.boxShadow = '0 2px 20px rgba(0, 0, 0, 0.1)';
        }
      });
    }
  }

  function getAuthConfig() {
    const cfgEl = qs('#js-config');
    if (cfgEl && cfgEl.dataset) {
      return {
        loggedIn: cfgEl.dataset.auth === '1',
        loginUrl: cfgEl.dataset.loginUrl || '/login',
        profileUrl: cfgEl.dataset.profileUrl || '/profile',
      };
    }
    const body = document.body;
    return {
      loggedIn: body?.dataset?.loggedIn === '1',
      loginUrl: body?.dataset?.loginUrl || '/login',
      profileUrl: body?.dataset?.profileUrl || '/profile',
    };
  }

  function initProfileButton() {
    const { loggedIn, loginUrl, profileUrl } = getAuthConfig();
    const btn = qs('.profile-btn');
    if (btn) btn.onclick = () => { window.location.href = loggedIn ? profileUrl : loginUrl; };

    // Ensure global handler exists for inline onclick usage in templates
    if (!window.handleProfileClick) {
      window.handleProfileClick = function () {
        const { loggedIn: li, loginUrl: lUrl, profileUrl: pUrl } = getAuthConfig();
        window.location.href = li ? pUrl : lUrl;
      };
    }
  }

  function playNotificationSound() {
    try {
      const audio = new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2/LDciUFLIHO8tiJNwgZaLvt559NEAxQp+PwtmMcBjiR1/LMeSwFJHfH8N2QQAoUXrTp66hVFApGn+DyvmwhBSuBzvLZiTYIG2m98OScTgwOUarm7blmGgU7k9n1unEiBC13yO/eizEIHWq+8+OWT');
      audio.play();
    } catch (e) { /* ignore */ }
  }

  function maybeInitAdminNotifications() {
    const body = document.body;
    const loggedIn = body?.dataset?.loggedIn === '1';
    if (!loggedIn) return;
    let intervalId;
    function checkNewReports() {
      fetch('/check-new-reports')
        .then(r => r.json())
        .then(data => {
          if (data.success && data.count > 0) {
            const latest = data.new_reports[0];
            const container = qs('#notification-container');
            if (container) {
              const typeEl = qs('#report-type');
              const nameEl = qs('#reporter-name');
              const dateEl = qs('#report-date');
              if (typeEl) typeEl.textContent = latest.type;
              if (nameEl) nameEl.textContent = latest.reporter_name;
              if (dateEl) dateEl.textContent = new Date(latest.date).toLocaleString('tr-TR');
              container.style.display = 'flex';
              playNotificationSound();
            }
          }
        })
        .catch(() => {});
    }
    fetch('/check-admin-status')
      .then(r => r.json())
      .then(d => {
        if (d.is_admin) {
          intervalId = setInterval(checkNewReports, 10000);
          checkNewReports();
        }
      })
      .catch(() => {});
    window.addEventListener('beforeunload', () => { if (intervalId) clearInterval(intervalId); });
  }

  function debugReports() {
    fetch('/debug-reports')
      .then(r => r.json())
      .then(data => {
        if (data.success) {
          console.log('=== DEBUG RAPORLARI ===');
          console.log('Mevcut Zaman:', data.current_time);
          console.log('Toplam Rapor:', data.total_reports);
          console.log('Yeni Rapor Sayısı:', data.new_reports_count);
          console.log('Tüm Raporlar:', data.all_reports);
          console.log('Yeni Raporlar:', data.new_reports);
          alert(`Debug Bilgileri:\nToplam Rapor: ${data.total_reports}\nYeni Rapor: ${data.new_reports_count}\nDetaylar için konsolu kontrol edin.`);
        } else {
          alert('Debug hatası: ' + data.message);
        }
      })
      .catch(err => alert('Debug hatası: ' + err.message));
  }

  window.SharedUI = {
    initNavbarUI,
    initProfileButton,
    maybeInitAdminNotifications,
    debugReports,
  };
  // Auto-init profile button on DOM ready for all pages
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initProfileButton);
  } else {
    initProfileButton();
  }
})();


