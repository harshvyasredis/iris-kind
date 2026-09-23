# Task 3: Add JavaScript

## Goal

Add interactivity to your page with JavaScript.

## Instructions

### Step 1: Open the JavaScript File

1. In VS Code, open `web/main.js`
2. You should see a simple console.log statement

### Step 2: Add a Button to HTML

First, add a button to your `index.html` inside the container:

```html
<button id="clickMe">Click Me!</button>
```

### Step 3: Add Click Handler

In `main.js`, add this code:

```javascript
const button = document.getElementById('clickMe');
let clickCount = 0;

button.addEventListener('click', () => {
    clickCount++;
    alert(`You clicked ${clickCount} times!`);
});
```

### Step 4: Test It

1. Save both files
2. Click the button in your app
3. You should see an alert!

## Challenge 1: Change the Text

Instead of an alert, can you change the heading text when clicked?

```javascript
const button = document.getElementById('clickMe');
const heading = document.querySelector('h1');

button.addEventListener('click', () => {
    heading.textContent = 'You clicked the button! 🎉';
});
```

## Challenge 2: Add Styling to the Button

Add this to your `style.css`:

```css
button {
    background: #667eea;
    color: white;
    border: none;
    padding: 1rem 2rem;
    border-radius: 0.5rem;
    font-size: 1rem;
    cursor: pointer;
    margin-top: 1rem;
}

button:hover {
    background: #5568d3;
}
```

## What You Learned

✅ How to add JavaScript interactivity  
✅ How to select DOM elements  
✅ How to handle click events  
✅ How to modify page content dynamically  

---

**Congratulations!** You've completed the basic tasks. Check the [Reference](/reference/reference.md) for more ideas!

