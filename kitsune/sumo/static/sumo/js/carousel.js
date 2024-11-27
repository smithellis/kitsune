document.addEventListener("DOMContentLoaded", function () {
    const carousel = document.querySelector('.carousel');
    if (!carousel) return;

    // Get all the necessary elements
    const previousButton = carousel.querySelector('.previous-button');
    const nextButton = carousel.querySelector('.next-button');
    const dynamicTitles = carousel.querySelectorAll('.dynamic-title');
    const itemTexts = carousel.querySelectorAll('.item-text');
    const staticImage = carousel.querySelector('.static-item-image');
    const textContainer = carousel.querySelector('.item-text-container');
    
    let currentIndex = 0;

    function updateActiveState(index) {
        // Update titles
        dynamicTitles.forEach((title, i) => {
            title.classList.toggle('active', i === index);
        });

        // Update content
        itemTexts.forEach((text, i) => {
            text.classList.toggle('active', i === index);
        });

        // Update button states
        previousButton.disabled = index === 0;
        nextButton.disabled = index === dynamicTitles.length - 1;
    }

    function moveToSlide(index) {
        if (index >= 0 && index < dynamicTitles.length) {
            currentIndex = index;
            updateActiveState(currentIndex);
        }
    }

    // Add click handlers for titles
    dynamicTitles.forEach((title, index) => {
        title.addEventListener('click', () => {
            moveToSlide(index);
        });
    });

    // Add click handlers for navigation buttons
    nextButton.addEventListener('click', () => {
        if (currentIndex < dynamicTitles.length - 1) {
            moveToSlide(currentIndex + 1);
        }
    });

    previousButton.addEventListener('click', () => {
        if (currentIndex > 0) {
            moveToSlide(currentIndex - 1);
        }
    });

    function updateTextContainerPadding() {
        if (window.innerWidth > 768) {
            const previousButtonWidth = previousButton.offsetWidth;
            const staticImageWidth = staticImage.offsetWidth;
            const totalPadding = previousButtonWidth + staticImageWidth;
            textContainer.style.paddingLeft = `${totalPadding}px`;
        } else {
            textContainer.style.paddingLeft = '0';
        }
    }

    // Initial setup
    updateActiveState(currentIndex);
    updateTextContainerPadding();

    // Update on window resize
    window.addEventListener('resize', updateTextContainerPadding);
});
  