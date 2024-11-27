document.addEventListener("DOMContentLoaded", function () {
    const track = document.querySelector(".carousel-track");
    const slides = Array.from(track.children);
    const nextButton = document.querySelector(".carousel-nav-button.next");
    const prevButton = document.querySelector(".carousel-nav-button.prev");
    const slideWidth = slides[0].getBoundingClientRect().width;
  
    // Arrange slides in a row
    slides.forEach((slide, index) => {
      slide.style.left = `${slideWidth * index}px`;
    });
  
    let currentIndex = 0;
  
    const moveToSlide = (track, currentIndex) => {
      const amountToMove = -slideWidth * currentIndex;
      track.style.transform = `translateX(${amountToMove}px)`;
    };
  
    nextButton.addEventListener("click", () => {
      if (currentIndex < slides.length - 1) {
        currentIndex++;
        moveToSlide(track, currentIndex);
      }
    });
  
    prevButton.addEventListener("click", () => {
      if (currentIndex > 0) {
        currentIndex--;
        moveToSlide(track, currentIndex);
      }
    });
  });
  