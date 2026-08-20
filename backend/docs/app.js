// NeuroOncoTrack-AI Security Architecture Portal Interactive Scripts

document.addEventListener('DOMContentLoaded', () => {
  // Navigation active highlighting on scroll
  const sections = document.querySelectorAll('.section-block');
  const navItems = document.querySelectorAll('.nav-item');
  const contentArea = document.querySelector('.content-area');

  const highlightNav = () => {
    let current = '';
    sections.forEach(section => {
      const sectionTop = section.offsetTop - contentArea.offsetTop - 80;
      if (contentArea.scrollTop >= sectionTop) {
        current = section.getAttribute('id');
      }
    });

    navItems.forEach(item => {
      item.classList.remove('active');
      if (item.getAttribute('href') === `#${current}`) {
        item.classList.add('active');
      }
    });
  };

  contentArea.addEventListener('scroll', highlightNav);

  // Smooth scroll to target section
  navItems.forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const targetId = item.getAttribute('href').substring(1);
      const targetElement = document.getElementById(targetId);
      if (targetElement) {
        targetElement.scrollIntoView({ behavior: 'smooth' });
      }
    });
  });

  // Search filtering
  const searchInput = document.getElementById('portalSearch');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      const query = e.target.value.toLowerCase().trim();
      
      sections.forEach(section => {
        const text = section.textContent.toLowerCase();
        if (query === '' || text.includes(query)) {
          section.style.display = 'block';
        } else {
          section.style.display = 'none';
        }
      });
    });
  }
});
